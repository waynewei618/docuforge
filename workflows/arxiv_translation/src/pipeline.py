"""主流水线编排：arxiv id / PDF → 英文 PDF + 中文 PDF。

run_pipeline() 串联：
  resolve_input → ensure_english_pdf → prepare_work → translate_work → build_chinese_pdf → collect_output
"""
from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import latex_fallbacks as lf
from .backends import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    build_backend,
)
from .tex_translator import TranslateOptions, translate_work, export_chunks_to_json, import_chunks_from_json


# ---------- 路径常量 ----------

SRC_DIR        = Path(__file__).resolve().parent
WORKFLOW_ROOT  = SRC_DIR.parent                # workflows/arxiv_translation/
PROJECT_ROOT   = WORKFLOW_ROOT.parents[1]      # 仓库根

TMP_ROOT       = WORKFLOW_ROOT / "tmp"
INBOX          = TMP_ROOT / "inbox"
WORK_ROOT      = TMP_ROOT / "work"
DEBUG_OUTBOX   = TMP_ROOT / "outbox"
OUTPUT_DEFAULT = PROJECT_ROOT / "outputs" / "arxiv_translation"
TEMPLATES      = WORKFLOW_ROOT / "templates"


# ---------- 结果 dataclass ----------

import xml.etree.ElementTree as ET
import re

_TITLE_SLUG_CACHE = {}

def get_arxiv_title_slug(arxiv_id: str) -> str:
    if arxiv_id in _TITLE_SLUG_CACHE:
        return _TITLE_SLUG_CACHE[arxiv_id]
        
    clean_id = arxiv_id.split('v')[0] if 'v' in arxiv_id else arxiv_id
    url = f"http://export.arxiv.org/api/query?id_list={clean_id}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'paper-translate/0.1'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entry = root.find('atom:entry', ns)
        if entry is not None:
            title_node = entry.find('atom:title', ns)
            if title_node is not None and title_node.text:
                title = title_node.text
                title = re.sub(r'\s+', ' ', title).strip()
                slug = re.sub(r'[^a-zA-Z0-9]+', '_', title).strip('_')
                _TITLE_SLUG_CACHE[arxiv_id] = slug
                return slug
    except Exception as e:
        print(f"[warn] 无法获取 {arxiv_id} 的标题: {e}", flush=True)
    
    _TITLE_SLUG_CACHE[arxiv_id] = ""
    return ""

@dataclass
class PipelineOptions:
    output_dir: Path = OUTPUT_DEFAULT
    force: bool = False
    prepare_only: bool = False
    compile_only: bool = False


@dataclass
class PipelineResult:
    arxiv_id: str
    english_pdf: Path | None = None
    chinese_pdf: Path | None = None
    skipped: bool = False
    work_dir: Path | None = None


# ---------- 输入解析 ----------

def _arxiv_id_from_name(value: str) -> str | None:
    match = re.search(r"(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?", value)
    return match.group(1) if match else None


def _normalize_arxiv_id(value: str) -> str:
    found = _arxiv_id_from_name(value)
    if not found:
        raise SystemExit(f"无法识别 arXiv ID：{value}")
    return found


def _safe_work_id(pdf: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    found = _arxiv_id_from_name(pdf.name)
    if found:
        return found
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", pdf.stem).strip("_")[:80]


def resolve_input(value: str) -> tuple[str, Path | None]:
    """接受 arxiv id / URL 或本地 PDF 路径，返回 (arxiv_id, source_pdf_or_None)。"""
    if value.lower().endswith(".pdf"):
        pdf_path = Path(value).expanduser().resolve()
        if pdf_path.exists():
            return _safe_work_id(pdf_path, None), pdf_path
    return _normalize_arxiv_id(value), None


# ---------- 通用工具 ----------

def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


def _run(cmd: list[str], cwd: Path | None = None, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print(f"[cmd] {' '.join(cmd)}", flush=True)
    kwargs: dict[str, object] = {"cwd": cwd, "text": True, "check": True}
    if capture:
        kwargs.update({"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT})
    return subprocess.run(cmd, **kwargs)


def _copy_if_needed(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dst.resolve():
        return
    shutil.copy2(src, dst)


def _is_project_source_pdf(path: Path) -> bool:
    try:
        rel_path = path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return False
    if rel_path.parts and rel_path.parts[0] in {"workflows", "docs", "output"}:
        return False
    if path.stem.endswith("_zh"):
        return False
    return path.suffix.lower() == ".pdf"


def _discover_pdfs() -> list[Path]:
    return [path for path in PROJECT_ROOT.rglob("*.pdf") if _is_project_source_pdf(path)]


def _find_source_pdf(arxiv_id: str) -> Path | None:
    matches = [path for path in _discover_pdfs() if _safe_work_id(path, None) == arxiv_id]
    return matches[0] if matches else None


# ---------- 下载 ----------

def _download_arxiv(arxiv_id: str, url_path: str, out_path: Path) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://arxiv.org/{url_path}"
    if shutil.which("curl"):
        try:
            _run([
                "curl", "-L", "-sS", "--fail", "--show-error",
                "--retry", "2", "--connect-timeout", "20", "--max-time", "300",
                "-A", "paper-translate/0.1",
                "-o", str(out_path), url,
            ])
            return out_path.exists() and out_path.stat().st_size > 0
        except subprocess.CalledProcessError as exc:
            detail = (exc.stdout or "").strip()
            print(f"[warn] curl 下载失败：{detail}")
            out_path.unlink(missing_ok=True)

    req = urllib.request.Request(url, headers={"User-Agent": "paper-translate/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            out_path.write_bytes(resp.read())
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception as exc:
        print(f"[warn] 下载失败：{exc}")
        out_path.unlink(missing_ok=True)
        return False


def download_arxiv_pdf(arxiv_id: str, out_pdf: Path) -> bool:
    return _download_arxiv(arxiv_id, f"pdf/{arxiv_id}.pdf", out_pdf)


def download_arxiv_source(arxiv_id: str, archive: Path) -> bool:
    return _download_arxiv(arxiv_id, f"e-print/{arxiv_id}", archive)


def _extract_source_archive(archive: Path, source_dir: Path) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive, "r:*") as tar:
            tar.extractall(source_dir, filter="data")
        return
    except tarfile.TarError:
        pass

    try:
        text = gzip.decompress(archive.read_bytes())
        (source_dir / "main.tex").write_bytes(text)
    except OSError as exc:
        raise RuntimeError(f"无法解包 arXiv 源码包：{archive}") from exc


def _extract_pdf_text(pdf: Path, out_txt: Path) -> bool:
    if shutil.which("pdftotext") is None:
        return False
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    try:
        _run(["pdftotext", "-layout", str(pdf), str(out_txt)])
        return True
    except subprocess.CalledProcessError as exc:
        detail = (exc.stdout or "").strip()
        print(f"[warn] pdftotext 提取失败：{detail}", flush=True)
        return False


def _find_main_tex(source_dir: Path) -> Path | None:
    candidates = list(source_dir.rglob("*.tex"))
    if not candidates:
        return None
    scored: list[tuple[int, Path]] = []
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="replace")
        score = 0
        if r"\documentclass" in text: score += 20
        if r"\begin{document}" in text: score += 20
        if r"\title" in text: score += 5
        if r"\begin{abstract}" in text: score += 5
        if r"\bibliography" in text or r"\begin{thebibliography}" in text: score += 5
        if path.name.lower() in {"main.tex", "paper.tex", "root.tex"}: score += 5
        scored.append((score, path))
    scored.sort(key=lambda item: (item[0], -len(item[1].parts)), reverse=True)
    return scored[0][1]


def _copy_source_tree(src: Path, dst: Path) -> None:
    ignored_names = {"main.pdf"}
    ignored_suffixes = {".aux", ".log", ".out", ".fls", ".fdb_latexmk", ".xdv"}
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        rel_item = item.relative_to(src)
        if item.is_dir():
            (dst / rel_item).mkdir(parents=True, exist_ok=True)
            continue
        if item.name in ignored_names or item.suffix in ignored_suffixes:
            continue
        target = dst / rel_item
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(item, target)


# ---------- 流水线 stage ----------

def ensure_english_pdf(arxiv_id: str, source_pdf: Path | None, output_dir: Path) -> tuple[Path, Path]:
    """确定/下载英文 PDF；复制到 output/<id>_<title>.pdf。"""
    if source_pdf is None:
        source_pdf = _find_source_pdf(arxiv_id)
    if source_pdf is None:
        source_pdf = INBOX / f"{arxiv_id}.pdf"
        if not source_pdf.exists():
            if not download_arxiv_pdf(arxiv_id, source_pdf):
                raise SystemExit(f"英文 PDF 下载失败：arXiv:{arxiv_id}")

    slug = get_arxiv_title_slug(arxiv_id)
    suffix = f"_{slug}.pdf" if slug else "_en.pdf"
    english_out = output_dir / f"{arxiv_id}{suffix}"
    _copy_if_needed(source_pdf, english_out)
    return source_pdf, english_out


def prepare_work(arxiv_id: str, source_pdf: Path, work: Path, opts: PipelineOptions) -> Path:
    """初始化 work/<id>/{source,zh,notes,...}。返回 zh/<main>.tex 路径。"""
    if work.exists() and opts.force:
        print(f"[prepare] 重建工作目录: {_rel(work)}", flush=True)
        shutil.rmtree(work)

    notes  = work / "notes"
    source = work / "source"
    zh     = work / "zh"
    for path in [INBOX, work, notes, zh]:
        path.mkdir(parents=True, exist_ok=True)

    # 仅当工作目录是首次创建或 force 时才做后续重设
    fresh = not (work / "metadata.json").exists() or opts.force

    inbox_pdf = INBOX / source_pdf.name
    work_pdf  = work / "input.pdf"
    if fresh:
        if source_pdf.resolve() != inbox_pdf.resolve():
            shutil.copy2(source_pdf, inbox_pdf)
        shutil.copy2(source_pdf, work_pdf)
        print(f"[prepare] 复制输入 PDF: {_rel(work_pdf)}", flush=True)

    source_status = "not_requested"
    main_tex: Path | None = None
    archive = work / "e-print.tar.gz"
    if fresh and re.fullmatch(r"\d{4}\.\d{4,5}", arxiv_id):
        print(f"[prepare] 下载 arXiv 源码: {arxiv_id}", flush=True)
        if download_arxiv_source(arxiv_id, archive):
            _extract_source_archive(archive, source)
            main_tex = _find_main_tex(source)
            source_status = "downloaded"
        else:
            source_status = "download_failed"
            print("[prepare] arXiv 源码下载失败，将使用 PDF 抽取", flush=True)
    elif (source / "*.tex") or any(source.rglob("*.tex")):
        # 复用已有 source/ （work 目录非 fresh 时）
        main_tex = _find_main_tex(source) if source.exists() else None
        source_status = "reused" if main_tex else source_status

    if fresh and main_tex is None and (work_pdf.exists()):
        extracted_txt = work / "extracted.txt"
        if _extract_pdf_text(work_pdf, extracted_txt):
            print(f"[prepare] 已提取 PDF 文本: {_rel(extracted_txt)}", flush=True)

    zh_main = zh / "main_zh.tex"
    if fresh:
        if main_tex is not None:
            print(f"[prepare] 检测到主 TeX: {_rel(main_tex)}", flush=True)
            _copy_source_tree(source, zh)
            updated = lf.normalize_optional_packages_in_dir(zh)
            if updated:
                print(f"[prepare] 已注入可选包降级兼容：{updated} 个 TeX 文件", flush=True)
            seed = main_tex.read_text(encoding="utf-8", errors="replace")
            seed = lf.use_existing_bbl_when_bib_missing(seed, source, main_tex)
            zh_main.write_text(lf.inject_chinese_preamble(seed), encoding="utf-8")
        else:
            print("[prepare] 未检测到主 TeX，使用降级模板", flush=True)
            zh_main.write_text(lf.FALLBACK_TEMPLATE, encoding="utf-8")

        template_rules = TEMPLATES / "translation_rules.md"
        if template_rules.exists():
            shutil.copy2(template_rules, notes / "translation_rules.md")

        (work / "metadata.json").write_text(
            json.dumps({
                "id": arxiv_id,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "source_pdf": _rel(source_pdf),
                "input_pdf": _rel(work_pdf),
                "source_status": source_status,
                "source_main_tex": _rel(main_tex) if main_tex else None,
                "zh_main_tex": _rel(zh_main),
                "status": "prepared",
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return zh_main


def build_chinese_pdf(work: Path, main: str) -> Path:
    """编译 zh/<main>.tex → build_zh/<main>.pdf，带自动 fallback 重试。"""
    zh  = work / "zh"
    tex = zh / main
    if not tex.exists():
        raise SystemExit(f"中文 TeX 不存在：{tex}")

    updated = lf.normalize_optional_packages_in_dir(zh)
    if updated:
        print(f"[build] 已补齐可选包兼容写法：{updated} 个 TeX 文件", flush=True)

    build_dir = work / "build_zh"
    print(f"[build] 开始编译: {_rel(tex)}", flush=True)

    max_attempts = 8
    last_exc: subprocess.CalledProcessError | None = None
    for attempt in range(1, max_attempts + 1):
        if build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True, exist_ok=True)
        if attempt > 1:
            print(f"[build] 第 {attempt} 次重试编译: {_rel(tex)}", flush=True)
        try:
            _run([
                "latexmk", "-xelatex",
                "-interaction=nonstopmode", "-halt-on-error",
                f"-outdir={build_dir.resolve()}",
                tex.name,
            ], cwd=zh)
            break
        except subprocess.CalledProcessError as exc:
            last_exc = exc
            log_path = build_dir / f"{tex.stem}.log"
            print(f"[build] 编译失败（第 {attempt} 次）", flush=True)
            lf.summarize_latex_failures(log_path)
            if attempt < max_attempts and lf.apply_auto_fallbacks_from_log(log_path, zh, tex):
                print("[build] 已应用可恢复补丁，尝试继续编译", flush=True)
                continue
            break

    pdf = build_dir / f"{tex.stem}.pdf"
    if not pdf.exists():
        raise SystemExit(f"未找到编译产物：{pdf}")

    if last_exc is not None:
        log_path = build_dir / f"{tex.stem}.log"
        if lf.is_nonfatal_latex_failure(log_path, pdf):
            print("[build] 编译完成（有非致命警告）", flush=True)
        else:
            raise SystemExit("中文 PDF 编译失败")
    return pdf


def collect_output(built_pdf: Path, zh_tex: Path, arxiv_id: str, output_dir: Path) -> Path:
    """复制中文 PDF 到 output/<id>_<title>_zh.pdf；同时归档到 tmp/outbox/。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = get_arxiv_title_slug(arxiv_id)
    suffix = f"_{slug}_zh.pdf" if slug else "_zh.pdf"
    chinese_out = output_dir / f"{arxiv_id}{suffix}"
    _copy_if_needed(built_pdf, chinese_out)

    DEBUG_OUTBOX.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built_pdf, DEBUG_OUTBOX / f"{arxiv_id}{suffix}")
    shutil.copy2(zh_tex,    DEBUG_OUTBOX / f"{arxiv_id}_zh.tex")
    return chinese_out


# ---------- 后端实例化 ----------

def _build_default_backend():
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("缺少 DEEPSEEK_API_KEY。请先配置该环境变量后再运行。")

    model = DEFAULT_DEEPSEEK_MODEL
    timeout = 120
    retries = 3
    base_url = DEFAULT_DEEPSEEK_BASE_URL

    backend = build_backend(
        "deepseek",
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.2,
        max_tokens=None,
        timeout=timeout,
        retries=retries,
    )
    return backend, model


# ---------- 主入口 ----------

def run_pipeline(input_value: str, opts: PipelineOptions) -> PipelineResult:
    arxiv_id, source_pdf_hint = resolve_input(input_value)
    output_dir = opts.output_dir.expanduser().resolve()

    # 如果是编译阶段，我们不检查 final_zh 是否已存在，因为用户明确发送了 compile 指令，通常是在更新了翻译后
    if opts.compile_only:
        work = WORK_ROOT / arxiv_id
        zh_main = work / "zh" / "main_zh.tex"
        if not zh_main.exists():
            raise SystemExit(f"工作目录中未找到 TeX 文件 {zh_main}，请先运行 --prepare")

        print(f"[compile] 开始从 JSON 导入译文：{arxiv_id}", flush=True)
        import_chunks_from_json(work)

        built_pdf = build_chinese_pdf(work, "main_zh.tex")
        chinese_out = collect_output(built_pdf, zh_main, arxiv_id, output_dir)
        return PipelineResult(
            arxiv_id=arxiv_id, english_pdf=None, chinese_pdf=chinese_out, work_dir=work,
        )

    # 幂等：已存在中文 PDF 且非 force，直接跳过翻译/编译（非 prepare_only 时生效）
    slug = get_arxiv_title_slug(arxiv_id)
    suffix = f"_{slug}_zh.pdf" if slug else "_zh.pdf"
    final_zh = output_dir / f"{arxiv_id}{suffix}"
    if not opts.force and final_zh.exists() and not opts.prepare_only:
        print(f"[skip] {arxiv_id}: 中文 PDF 已存在 {_rel(final_zh)}（用 --force 重做）", flush=True)
        try:
            _, english_out = ensure_english_pdf(arxiv_id, source_pdf_hint, output_dir)
        except SystemExit:
            english_out = None
        return PipelineResult(
            arxiv_id=arxiv_id, english_pdf=english_out, chinese_pdf=final_zh, skipped=True,
        )

    work = WORK_ROOT / arxiv_id

    # 1. 英文 PDF（落入 output/<id>_en.pdf）
    source_pdf, english_out = ensure_english_pdf(arxiv_id, source_pdf_hint, output_dir)

    # 2. 准备工作目录（解包 e-print / 初始化 zh/main_zh.tex）
    zh_main = prepare_work(arxiv_id, source_pdf, work, opts)

    # 如果是只准备阶段，我们在这里导出 chunks 后直接返回
    if opts.prepare_only:
        translate_opts = TranslateOptions(
            main="main_zh.tex",
            main_only=False,
            limit_chunks=None,
            force=opts.force,
            sleep=0.0,
        )
        export_chunks_to_json(work, translate_opts, PROJECT_ROOT)
        return PipelineResult(
            arxiv_id=arxiv_id, english_pdf=english_out, chinese_pdf=None, work_dir=work,
        )

    # 3. 翻译
    backend, backend_model = _build_default_backend()
    translate_opts = TranslateOptions(
        main="main_zh.tex",
        main_only=False,
        limit_chunks=None,
        force=opts.force,
        sleep=0.0,
    )
    translate_work(
        work=work,
        backend=backend,
        opts=translate_opts,
        templates_dir=TEMPLATES,
        project_root=PROJECT_ROOT,
        backend_model=backend_model,
    )

    # 4. 编译
    built_pdf = build_chinese_pdf(work, "main_zh.tex")

    # 5. 落产物
    chinese_out = collect_output(built_pdf, zh_main, arxiv_id, output_dir)
    return PipelineResult(
        arxiv_id=arxiv_id, english_pdf=english_out, chinese_pdf=chinese_out, work_dir=work,
    )
