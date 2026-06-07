#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import os
import json
import re
import shutil
import subprocess
import tarfile
import urllib.request
from datetime import datetime
from pathlib import Path


SCRIPT = Path(__file__).resolve()
WORKFLOW_ROOT = SCRIPT.parents[1]
PROJECT_ROOT = SCRIPT.parents[3]
WORKSPACE_ROOT = PROJECT_ROOT / "workspace" / "arxiv_translation"
INBOX = WORKSPACE_ROOT / "inbox"
WORK_ROOT = WORKSPACE_ROOT / "work"
OUTBOX = WORKSPACE_ROOT / "outbox"
TEMPLATE_RULES = WORKFLOW_ROOT / "templates" / "translation_rules.md"
UNPUBLISHED_DIR_NAME = "未查到正式发表信息"

IFSYM_FALLBACK = r"""\IfFileExists{ifsym.sty}{\usepackage[misc]{ifsym}}{%
% Auto fallback for missing ifsym.sty: keep compileable in environments without ifsym.
  \providecommand{\Letter}{\ensuremath{\star}}
  \providecommand{\Square}{\ensuremath{\square}}
  \providecommand{\Circle}{\ensuremath{\bullet}}
  \providecommand{\CIRCLE}{\ensuremath{\bullet}}
  \providecommand{\Diamondsuit}{\diamond}
  \providecommand{\X}{\times}
}"""

XELATEX_ENCODING_FALLBACK = (
    "% {line}\n"
    "% Auto XeLaTeX compatibility: legacy utf8/font encoding packages are unnecessary."
)

MISSING_PKG_HINTS = {
    "bbm.sty": "sudo apt install -y texlive-fonts-extra",
    "ifsym.sty": "sudo apt install -y texlive-science texlive-latex-extra",
    "bbding.sty": "sudo apt install -y texlive-latex-extra",
    "xcolor.sty": "sudo apt install -y texlive-latex-recommended",
    "ctex.sty": "sudo apt install -y texlive-lang-chinese texlive-latex-extra",
    "xeCJK.sty": "sudo apt install -y texlive-xetex texlive-lang-chinese",
}

UNDEFINED_COMMAND_FALLBACKS = {
    "ignorespaces": "\\providecommand{\\ignorespaces}{}\n",
    "acronym": (
        "\\providecommand{\\acronym}{}\n"
    ),
    "pdfcompresslevel": (
        "\\newcount\\pdfcompresslevel\n"
        "\\pdfcompresslevel=0\n"
        "% XeLaTeX 下部分样式文件会直接写入该原始 pdfTeX 寄存器；"
        " 使用计数寄存器占位可避免 undefined control sequence 崩溃。"
    ),
    "pdfobjcompresslevel": (
        "\\newcount\\pdfobjcompresslevel\n"
        "\\pdfobjcompresslevel=3\n"
        "% 与 pdfcompresslevel 类似的兼容兜底定义。"
    ),
    "pdfminorversion": (
        "\\newcount\\pdfminorversion\n"
        "\\pdfminorversion=5\n"
    ),
    "pdfoptionpdfminorversion": (
        "\\newcount\\pdfoptionpdfminorversion\n"
        "\\pdfoptionpdfminorversion=6\n"
    ),
    "pdfglyphtounicode": (
        "\\ifx\\pdfglyphtounicode\\undefined\\def\\pdfglyphtounicode#1#2{}\\fi\n"
    ),
    "pdfgentounicode": (
        "\\ifx\\pdfgentounicode\\undefined\\newcount\\pdfgentounicode\\fi\n"
    ),
    "Checkmark": (
        "\\providecommand{\\Checkmark}{\\checkmark}\n"
    ),
    "CheckmarkBold": (
        "\\providecommand{\\CheckmarkBold}{\\checkmark}\n"
    ),
    "XSolidBrush": (
        "\\providecommand{\\XSolidBrush}{\\ensuremath{\\times}}\n"
    ),
    "xmark": (
        "\\providecommand{\\xmark}{\\ensuremath{\\times}}\n"
    ),
    "cmark": (
        "\\providecommand{\\cmark}{\\checkmark}\n"
    ),
}

BBDING_FALLBACK = (
    "% Auto fallback: bbding.sty not found, use plain symbol fallback.\n"
    "% bbding 常见符号在不完整环境中的兼容定义。\n"
    "\\providecommand{\\Checkmark}{\\checkmark}\n"
    "\\providecommand{\\CheckmarkBold}{\\checkmark}\n"
    "\\providecommand{\\cmark}{\\checkmark}\n"
    "\\providecommand{\\xmark}{\\ensuremath{\\times}}\n"
    "\\providecommand{\\XSolidBrush}{\\ensuremath{\\times}}\n"
)


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


def run(cmd: list[str], cwd: Path | None = None, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print(f"[cmd] {' '.join(cmd)}", flush=True)
    kwargs = {
        "cwd": cwd,
        "text": True,
        "check": True,
    }
    if capture:
        kwargs.update({"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT})
    return subprocess.run(cmd, **kwargs)


def has_command_definition(tex: str, command: str) -> bool:
    command = command.lstrip("\\")
    escaped = re.escape(command)
    patterns = [
        rf"\\(?:newcommand|renewcommand|providecommand)\*?\s*\{{\\{escaped}\}}",
        rf"\\DeclareRobustCommand\*?\s*\{{\\{escaped}\}}",
        rf"\\newcount\\{escaped}\b",
        rf"\\def\\{escaped}\b",
        rf"\\edef\\{escaped}\b",
        rf"\\xdef\\{escaped}\b",
        rf"\\let\\{escaped}\s*=?",
    ]
    return any(re.search(pattern, tex, flags=re.MULTILINE) is not None for pattern in patterns)


def inject_missing_command_fallbacks(main_tex: Path, missing_commands: list[str]) -> bool:
    if not missing_commands:
        return False
    if not main_tex.exists():
        return False

    text = main_tex.read_text(encoding="utf-8", errors="replace")
    documentclass_match = re.search(r"(?m)^\\documentclass(?:\[[^]]*\])?\{[^}]+\}\s*$", text)
    begin_document_match = re.search(r"(?m)^\\begin\\{document\\}\s*$", text)
    if documentclass_match is None and begin_document_match is None:
        return False

    insertion_idx = documentclass_match.end() if documentclass_match else begin_document_match.start()
    preamble = text[:insertion_idx]
    insertion_token = text[insertion_idx:]
    block_lines: list[str] = []
    for command in missing_commands:
        cmd = command.lstrip("\\")
        if cmd in UNDEFINED_COMMAND_FALLBACKS and cmd not in {"", "begin", "end"}:
            if not has_command_definition(text, cmd):
                block_lines.append(UNDEFINED_COMMAND_FALLBACKS[cmd])

    if not block_lines:
        return False

    fallback_block = "\n\n% Auto fallback: keep compileable for translated control sequences.\n" + "\n".join(block_lines) + "\n"
    updated = preamble + fallback_block + insertion_token
    main_tex.write_text(updated, encoding="utf-8")
    return True


def normalize_cjk_adjacent_macros(tex_root: Path, commands: list[str]) -> bool:
    if not commands:
        return False

    changed = False
    for path in sorted(tex_root.glob("**/*.tex")):
        text = path.read_text(encoding="utf-8", errors="replace")
        fixed = text
        for command in commands:
            cmd = command.lstrip("\\")
            if not cmd or cmd in {"begin", "end"}:
                continue
            # 在 XeTeX + CJK 组合下，中文字符可能会被当作命令后续字符，导致 \macro中文 解析失败。
            # 在 `\macro中文` 和 `\macro\中文` 两种常见形态下都补齐空参数。
            pattern = re.compile(rf"\\{re.escape(cmd)}(?=[\u4e00-\u9fff])")
            fixed = pattern.sub(rf"\\{cmd}{{}}", fixed)
            pattern = re.compile(rf"\\{re.escape(cmd)}\\(?=[\u4e00-\u9fff])")
            fixed = pattern.sub(rf"\\{cmd}{{}}", fixed)

        if fixed != text:
            path.write_text(fixed, encoding="utf-8")
            changed = True

    return changed


def arxiv_id_from_name(path: Path) -> str | None:
    match = re.search(r"(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?", path.name)
    return match.group(1) if match else None


def normalize_arxiv_id(value: str) -> str:
    match = re.search(r"(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?", value)
    if not match:
        raise SystemExit(f"无法识别 arXiv ID：{value}")
    return match.group(1)


def is_project_source_pdf(path: Path) -> bool:
    try:
        rel_path = path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return False
    if rel_path.parts and rel_path.parts[0] in {"workspace", "workflows", "docs"}:
        return False
    if path.stem.endswith("_zh"):
        return False
    return path.suffix.lower() == ".pdf"


def publication_group(path: Path) -> str:
    return "unpublished" if UNPUBLISHED_DIR_NAME in path.parts else "published"


def discover_pdfs() -> list[Path]:
    pdfs = [path for path in PROJECT_ROOT.rglob("*.pdf") if is_project_source_pdf(path)]
    pdfs.sort(
        key=lambda path: (
            1 if publication_group(path) == "unpublished" else 0,
            rel(path),
        )
    )
    return pdfs


def find_source_pdf(work_id: str) -> Path | None:
    normalized = normalize_arxiv_id(work_id) if re.search(r"\d{4}\.\d{4,5}", work_id) else work_id
    matches = [path for path in discover_pdfs() if safe_work_id(path, None) == normalized]
    return matches[0] if matches else None


def source_output_path(source_pdf: Path, work_id: str) -> Path:
    if arxiv_id_from_name(source_pdf):
        return source_pdf.with_name(f"{source_pdf.stem}_zh.pdf")
    return source_pdf.with_name(f"{work_id}_zh.pdf")


def safe_work_id(pdf: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    found = arxiv_id_from_name(pdf)
    if found:
        return found
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", pdf.stem).strip("_")[:80]


def find_main_tex(source_dir: Path) -> Path | None:
    candidates = list(source_dir.rglob("*.tex"))
    if not candidates:
        return None
    scored: list[tuple[int, Path]] = []
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="replace")
        score = 0
        if r"\documentclass" in text:
            score += 20
        if r"\begin{document}" in text:
            score += 20
        if r"\title" in text:
            score += 5
        if r"\begin{abstract}" in text:
            score += 5
        if r"\bibliography" in text or r"\begin{thebibliography}" in text:
            score += 5
        if path.name.lower() in {"main.tex", "paper.tex", "root.tex"}:
            score += 5
        scored.append((score, path))
    scored.sort(key=lambda item: (item[0], -len(item[1].parts)), reverse=True)
    return scored[0][1]


def normalize_optional_packages(tex: str) -> str:
    tex = re.sub(
        r"(?m)^(?!\s*%)\\usepackage(?:\[[^]]*\])?\{ifsym\}\s*$",
        lambda _match: IFSYM_FALLBACK,
        tex,
    )
    tex = re.sub(
        r"(?m)^(?!\s*%)\\usepackage(?:\[[^]]*\])?\{bbding\}\s*$",
        lambda _match: BBDING_FALLBACK,
        tex,
    )
    tex = re.sub(
        r"(?m)^(?!\s*%)\\usepackage\{bbm\}\s*$",
        lambda _match: r"% \usepackage{bbm}\n\providecommand{\mathbbm}[1]{\mathbb{#1}}",
        tex,
    )
    return tex


def normalize_xelatex_encoding(tex: str) -> str:
    tex = re.sub(
        r"(?m)^(?!\s*%)\\usepackage\[[^]]*\]\{inputenc\}\s*(%.*)?$",
        lambda m: XELATEX_ENCODING_FALLBACK.format(
            line=m.group(0).strip() + " (已在 XeLaTeX 下注释以兼容中文字体栈)"
        ),
        tex,
    )
    tex = re.sub(
        r"(?m)^(?!\s*%)\\usepackage(?:\[[^]]*\])?\{fontenc\}\s*(%.*)?$",
        lambda m: XELATEX_ENCODING_FALLBACK.format(
            line=m.group(0).strip() + " (已在 XeLaTeX 下注释以兼容中文字体栈)"
        ),
        tex,
    )
    return tex


def inject_chinese_preamble(tex: str) -> str:
    if r"\usepackage" in tex and "ctex" in tex:
        return tex
    is_acmart = re.search(r"\\documentclass(?:\[[^\]]*\])?\{acmart\}", tex) is not None
    cjk_lines = []
    if not is_acmart:
        cjk_lines.append(r"\usepackage[UTF8,fontset=none]{ctex}")
    cjk_lines.extend(
        [
            r"\usepackage{fontspec}",
            r"\usepackage{xeCJK}",
            r"\setCJKmainfont{Noto Serif CJK SC}",
            r"\setCJKsansfont{Noto Sans CJK SC}",
            r"\setCJKmonofont{Noto Sans Mono CJK SC}",
            r"\setlength{\columnsep}{0.30in}",
            r"\setlength{\columnseprule}{0.35pt}",
        ]
    )
    cjk = "\n".join(cjk_lines)
    pattern = re.compile(r"^(?!\s*%)(.*\\documentclass(?:\[[^\]]*\])?\{[^}]+\}.*)$", re.MULTILINE)
    return pattern.sub(
        lambda match: match.group(1) + "\n" + cjk,
        normalize_xelatex_encoding(normalize_optional_packages(tex)),
        count=1,
    )


def normalize_optional_packages_in_dir(tex_root: Path) -> int:
    updated = 0
    for path in sorted(tex_root.rglob("*.tex")):
        text = path.read_text(encoding="utf-8", errors="replace")
        normalized = normalize_xelatex_encoding(normalize_optional_packages(text))
        if normalized != text:
            path.write_text(normalized, encoding="utf-8")
            updated += 1
    return updated


def use_existing_bbl_when_bib_missing(tex: str, source_dir: Path, main_tex: Path) -> str:
    bib_files = list(source_dir.rglob("*.bib"))
    if bib_files:
        return tex

    bbl = main_tex.with_suffix(".bbl")
    if not bbl.exists():
        return tex

    try:
        bbl_input = bbl.relative_to(source_dir).as_posix()
    except ValueError:
        bbl_input = bbl.name

    replacement = "{\n\\input{" + bbl_input + "}\n}"
    replace_fn = lambda _match: replacement
    block_re = re.compile(
        r"\{\s*\\bibliographystyle\{[^}]+\}\s*\\bibliography\{[^}]+\}\s*\}",
        flags=re.DOTALL,
    )
    if block_re.search(tex):
        return block_re.sub(replace_fn, tex, count=1)

    return re.sub(
        r"\\bibliographystyle\{[^}]+\}\s*\\bibliography\{[^}]+\}",
        replace_fn,
        tex,
        count=1,
        flags=re.DOTALL,
    )


def copy_source_tree(src: Path, dst: Path) -> None:
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


def extract_source_archive(archive: Path, source_dir: Path) -> None:
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


def download_arxiv_source(arxiv_id: str, archive: Path) -> bool:
    archive.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://arxiv.org/e-print/{arxiv_id}"
    if shutil.which("curl"):
        try:
            run(
                [
                    "curl",
                    "-L",
                    "-sS",
                    "--fail",
                    "--show-error",
                    "--retry",
                    "2",
                    "--connect-timeout",
                    "20",
                    "--max-time",
                    "300",
                    "-A",
                    "paper-translate/0.1",
                    "-o",
                str(archive),
                    url,
                ]
            )
            return archive.exists() and archive.stat().st_size > 0
        except subprocess.CalledProcessError as exc:
            detail = (exc.stdout or "").strip()
            print(f"[warn] arXiv 源码 curl 下载失败：{detail}")
            archive.unlink(missing_ok=True)

    req = urllib.request.Request(url, headers={"User-Agent": "paper-translate/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            archive.write_bytes(resp.read())
        return True
    except Exception as exc:
        print(f"[warn] arXiv 源码下载失败：{exc}")
        return False


def download_arxiv_pdf(arxiv_id: str, out_pdf: Path) -> bool:
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    if shutil.which("curl"):
        try:
            run(
                [
                    "curl",
                    "-L",
                    "-sS",
                    "--fail",
                    "--show-error",
                    "--retry",
                    "2",
                    "--connect-timeout",
                    "20",
                    "--max-time",
                    "300",
                    "-A",
                    "paper-translate/0.1",
                    "-o",
                    str(out_pdf),
                    url,
                ]
            )
            return out_pdf.exists() and out_pdf.stat().st_size > 0
        except subprocess.CalledProcessError as exc:
            detail = (exc.stdout or "").strip()
            print(f"[warn] arXiv PDF curl 下载失败：{detail}")
            out_pdf.unlink(missing_ok=True)

    req = urllib.request.Request(url, headers={"User-Agent": "paper-translate/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            out_pdf.write_bytes(resp.read())
        return out_pdf.exists() and out_pdf.stat().st_size > 0
    except Exception as exc:
        print(f"[warn] arXiv PDF 下载失败：{exc}")
        out_pdf.unlink(missing_ok=True)
        return False


def extract_pdf_text(pdf: Path, out_txt: Path) -> bool:
    if shutil.which("pdftotext") is None:
        return False
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    try:
        run(["pdftotext", "-layout", str(pdf), str(out_txt)])
        return True
    except subprocess.CalledProcessError as exc:
        detail = (exc.stdout or "").strip()
        print(f"[warn] pdftotext 提取失败：{detail}", flush=True)
        return False


def write_metadata(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def list_papers(args: argparse.Namespace) -> None:
    rows = []
    for index, pdf in enumerate(discover_pdfs(), start=1):
        group = publication_group(pdf)
        if args.published_only and group != "published":
            continue
        if args.unpublished_only and group != "unpublished":
            continue
        work_id = safe_work_id(pdf, None)
        work = WORK_ROOT / work_id
        out_pdf = OUTBOX / f"{work_id}_zh.pdf"
        rows.append(
            {
                "index": index,
                "id": work_id,
                "group": group,
                "prepared": work.exists(),
                "built": out_pdf.exists(),
                "pdf": rel(pdf),
            }
        )

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    for row in rows:
        group_label = "有发表信息" if row["group"] == "published" else "未查到正式发表信息"
        state = "built" if row["built"] else "prepared" if row["prepared"] else "new"
        print(f"{row['index']:03d} {row['id']} [{group_label}] [{state}] {row['pdf']}")


def prepare(args: argparse.Namespace) -> None:
    pdf = Path(args.pdf).expanduser().resolve()
    if not pdf.exists():
        raise SystemExit(f"输入 PDF 不存在：{pdf}")

    work_id = safe_work_id(pdf, args.arxiv_id)
    print(f"[prepare] 开始处理: {work_id}", flush=True)
    work = WORK_ROOT / work_id
    if work.exists() and not args.force:
        raise SystemExit(f"工作目录已存在，拒绝覆盖：{work}\n如需重建，请显式添加 --force。")
    if work.exists() and args.force:
        print(f"[prepare] 重建工作目录: {rel(work)}", flush=True)
        shutil.rmtree(work)

    notes = work / "notes"
    source = work / "source"
    zh = work / "zh"
    for path in [INBOX, OUTBOX, work, notes, zh]:
        path.mkdir(parents=True, exist_ok=True)
    print(f"[prepare] 已初始化目录: {rel(work)}", flush=True)

    inbox_pdf = INBOX / pdf.name
    work_pdf = work / "input.pdf"
    if pdf.resolve() != inbox_pdf.resolve():
        shutil.copy2(pdf, inbox_pdf)
        print(f"[prepare] 复制输入 PDF 到 inbox: {rel(inbox_pdf)}", flush=True)
    shutil.copy2(pdf, work_pdf)
    print(f"[prepare] 复制输入 PDF 到工作目录: {rel(work_pdf)}", flush=True)

    source_status = "not_requested"
    archive = work / "e-print.tar.gz"
    main_tex: Path | None = None
    if args.download_source and re.fullmatch(r"\d{4}\.\d{4,5}", work_id):
        print(f"[prepare] 尝试下载 arXiv 源码: {work_id}", flush=True)
        if download_arxiv_source(work_id, archive):
            extract_source_archive(archive, source)
            source_status = "downloaded"
            main_tex = find_main_tex(source)
            print(f"[prepare] 源码下载/解压完成: {rel(archive)}", flush=True)
        else:
            source_status = "download_failed"
            print("[prepare] arXiv 源码下载失败，将使用 PDF 抽取", flush=True)

    extracted_txt = work / "extracted.txt"
    extracted = False
    if main_tex is None:
        extracted = extract_pdf_text(work_pdf, extracted_txt)
        if extracted:
            print(f"[prepare] 已提取 PDF 文本: {rel(extracted_txt)}", flush=True)
        else:
            print("[prepare] PDF 文本提取失败或不可用", flush=True)

    if main_tex is not None:
        print(f"[prepare] 检测到主 TeX: {rel(main_tex)}", flush=True)
        copy_source_tree(source, zh)
        updated = normalize_optional_packages_in_dir(zh)
        if updated:
            print(f"[prepare] 已注入可选包降级兼容：{updated} 个 TeX 文件", flush=True)
        zh_main = zh / "main_zh.tex"
        seed = main_tex.read_text(encoding="utf-8", errors="replace")
        seed = use_existing_bbl_when_bib_missing(seed, source, main_tex)
        zh_main.write_text(inject_chinese_preamble(seed), encoding="utf-8")
    else:
        print("[prepare] 未检测到主 TeX，使用降级模板", flush=True)
        zh_main = zh / "main_zh.tex"
        zh_main.write_text(
            "\n".join(
                [
                    r"\documentclass[UTF8]{ctexart}",
                    r"\usepackage{graphicx}",
                    r"\usepackage{amsmath,amssymb}",
                    r"\usepackage[colorlinks=true, linkcolor=black, citecolor=blue, urlcolor=blue]{hyperref}",
                    r"\begin{document}",
                    r"\title{待翻译标题}",
                    r"\author{}",
                    r"\maketitle",
                    r"% 源码不可用时，请根据 ../extracted.txt 在这里重建中文正文。",
                    r"\end{document}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    if TEMPLATE_RULES.exists():
        shutil.copy2(TEMPLATE_RULES, notes / "translation_rules.md")
    (notes / "codex_task.md").write_text(
        "\n".join(
            [
                f"# {work_id} 翻译任务",
                "",
                f"- 输入 PDF：`{rel(work_pdf)}`",
                f"- 英文源码：`{rel(source)}`" if main_tex else "- 英文源码：未找到，使用 PDF 抽取文本降级",
                f"- 中文 TeX：`{rel(zh_main)}`",
                "",
                "Codex 流水线：请在当前 Codex 会话内翻译中文 TeX，保持公式、引用、图表编号和图片路径可编译。",
                "",
                "DeepSeek API 流水线：",
                "",
                "```bash",
                "export DEEPSEEK_API_KEY='sk-...'",
                f"python workflows/arxiv_translation/scripts/deepseek_translate_tex.py translate {work_id} --build",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    write_metadata(
        work / "metadata.json",
        {
            "id": work_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source_pdf": rel(pdf),
            "input_pdf": rel(work_pdf),
            "inbox_pdf": rel(inbox_pdf),
            "source_status": source_status,
            "source_main_tex": rel(main_tex) if main_tex else None,
            "pdf_text_extracted": extracted,
            "zh_main_tex": rel(zh_main),
            "status": "prepared",
        },
    )

    print(f"[prepare] 已准备完成: {rel(work)}", flush=True)
    print(f"[prepare] 主中文 TeX: {rel(zh_main)}", flush=True)
    print(f"[prepare] 规则文件: {rel(notes / 'translation_rules.md')}", flush=True)


def prepare_batch(args: argparse.Namespace) -> None:
    prepared = 0
    skipped = 0
    failed = 0
    selected = 0

    for pdf in discover_pdfs():
        group = publication_group(pdf)
        if args.published_only and group != "published":
            continue
        if args.unpublished_only and group != "unpublished":
            continue
        if not args.include_unpublished and group == "unpublished":
            continue
        if args.limit and selected >= args.limit:
            break

        selected += 1
        work_id = safe_work_id(pdf, None)
        work = WORK_ROOT / work_id
        if work.exists() and not args.force:
            if (work / "metadata.json").exists():
                skipped += 1
                print(f"[skip] {work_id}: 工作目录已存在")
                continue
            print(f"[repair] {work_id}: 清理未完成的工作目录")
            shutil.rmtree(work)

        print(f"[prepare] {work_id}: {rel(pdf)}")
        batch_args = argparse.Namespace(
            pdf=str(pdf),
            arxiv_id=None,
            download_source=args.download_source,
            force=args.force,
        )
        try:
            prepare(batch_args)
            prepared += 1
        except Exception as exc:
            failed += 1
            print(f"[fail] {work_id}: {exc}")

    print(f"summary: selected={selected} prepared={prepared} skipped={skipped} failed={failed}")


def api_translate(args: argparse.Namespace) -> None:
    pdf = Path(args.pdf).expanduser().resolve()
    if not pdf.exists():
        raise SystemExit(f"输入 PDF 不存在：{pdf}")

    work_id = safe_work_id(pdf, args.arxiv_id)
    work = WORK_ROOT / work_id
    print(f"[api] 任务开始: {work_id}", flush=True)
    if work.exists():
        if not args.reuse_work and not args.force_prepare:
            raise SystemExit(
                f"工作目录已存在：{work}\n"
                "如需沿用现有工作目录，请添加 --reuse-work；如需重建，请添加 --force-prepare。"
            )
        if args.force_prepare:
            print("[api] 检测到 --force-prepare，重建工作目录", flush=True)
            prepare(
                argparse.Namespace(
                    pdf=str(pdf),
                    arxiv_id=args.arxiv_id,
                    download_source=args.download_source,
                    force=True,
                )
            )
        else:
            print(f"[api] 使用现有工作目录: {rel(work)}", flush=True)
    else:
        print(f"[api] 未检测到工作目录，执行 prepare: {rel(work)}", flush=True)
        prepare(
            argparse.Namespace(
                pdf=str(pdf),
                arxiv_id=args.arxiv_id,
                download_source=args.download_source,
                force=False,
            )
        )

    cmd = [
        "python",
        "-u",
        str(WORKFLOW_ROOT / "scripts" / "deepseek_translate_tex.py"),
        "translate",
        work_id,
        "--main",
        args.main,
    ]
    if not args.dry_run:
        cmd.append("--build")
    if args.dry_run:
        cmd.append("--dry-run")
    if args.main_only:
        cmd.append("--main-only")
    if args.force_translate:
        cmd.append("--force")
    if args.limit_chunks is not None:
        cmd.extend(["--limit-chunks", str(args.limit_chunks)])
    if args.timeout is not None:
        cmd.extend(["--timeout", str(args.timeout)])
    if args.retries is not None:
        cmd.extend(["--retries", str(args.retries)])
    if args.sleep > 0:
        cmd.extend(["--sleep", str(args.sleep)])
    if args.max_tokens is not None:
        cmd.extend(["--max-tokens", str(args.max_tokens)])
    if args.model:
        cmd.extend(["--model", args.model])
    if args.base_url:
        cmd.extend(["--base-url", args.base_url])
    if args.temperature is not None:
        cmd.extend(["--temperature", str(args.temperature)])

    print(f"[api] 调用翻译器: {' '.join(cmd)}", flush=True)
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            "[api] 翻译器执行失败，返回码="
            f"{result.returncode}。请先确保 DEEPSEEK_API_KEY 已通过 .bashrc 或 --api-key 提供。"
        )


def resolve_output_dir(output_dir: str | None) -> Path:
    if output_dir:
        path = Path(output_dir).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()
    return OUTBOX


def copy_if_needed(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dst.resolve():
        return
    shutil.copy2(src, dst)


def ensure_english_pdf(arxiv_id: str, output_dir: Path, force_download: bool) -> tuple[Path, Path]:
    source_pdf = None if force_download else find_source_pdf(arxiv_id)
    if source_pdf is None:
        source_pdf = INBOX / f"{arxiv_id}.pdf"
        if force_download or not source_pdf.exists():
            if not download_arxiv_pdf(arxiv_id, source_pdf):
                raise SystemExit(f"英文 PDF 下载失败：arXiv:{arxiv_id}")

    english_out = output_dir / f"{arxiv_id}_en.pdf"
    copy_if_needed(source_pdf, english_out)
    return source_pdf, english_out


def summarize_latex_failures(log_path: Path) -> None:
    if not log_path.exists():
        print(f"[build] 编译日志未生成：{rel(log_path)}")
        return

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    missing_files = []
    missing_commands = []

    for idx, line in enumerate(lines):
        missing_match = re.search(
            r"^!?\s*(?:LaTeX Error: File `([^']+)'\s*not found\.|I can't find file `([^']+)'\.)$",
            line,
        )
        if missing_match:
            missing_files.append(next(name for name in missing_match.groups() if name))

        if "Undefined control sequence." in line:
            for j in range(idx, min(idx + 6, len(lines))):
                next_match = re.search(r"(\\[A-Za-z@]+)(?=[^A-Za-z@]|$)", lines[j])
                if next_match:
                    missing_commands.append(next_match.group(1))
                    break

    if missing_files:
        print("[build] 检测到缺失宏包文件:")
        for item in sorted(set(missing_files)):
            msg = MISSING_PKG_HINTS.get(item, "")
            if msg:
                print(f"  - {item}（建议执行: {msg}）")
            else:
                print(f"  - {item}")

    if missing_commands:
        print("[build] 检测到未定义命令:")
        for item in sorted(set(missing_commands)):
            print(f"  - {item}")

    if not missing_files and not missing_commands:
        tail = "\n".join(lines[-30:])
        print(f"[build] LaTeX 失败片段（最近 30 行）:\n{tail}")


def parse_latex_failures(log_path: Path) -> tuple[list[str], list[str], bool, list[str], bool]:
    if not log_path.exists():
        return [], [], False, [], False

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    missing_files = []
    missing_commands = []
    has_xelatex_glyph_error = False
    glyph_fonts: list[str] = []

    for idx, line in enumerate(lines):
        missing_match = re.search(
            r"^!?\s*(?:LaTeX Error: File `([^']+)'\s*not found\.|I can't find file `([^']+)'\.)$",
            line,
        )
        if missing_match:
            missing_files.append(next(name for name in missing_match.groups() if name))

        if "Undefined control sequence." in line:
            for j in range(idx, min(idx + 6, len(lines))):
                missing_commands.extend(
                    [
                        "\\" + m.group(1)
                        for m in re.finditer(r"\\([A-Za-z@]+)(?=[^A-Za-z@]|$)", lines[j])
                    ]
                )

        glyph_match = re.search(r"Cannot use XeTeXglyph with (.+); not a native platform font\.", line)
        if glyph_match:
            has_xelatex_glyph_error = True
            glyph_fonts.append(glyph_match.group(1).strip())

    has_bibtex_error = any(
        "I was expecting a `" in line
        or "I was expecting a `" in line
        or "Error--" in line and "a `,'" in line
        or "I don't understand this entry" in line
        for line in lines
    )
    has_bibtex_error = has_bibtex_error or any(
        "Fatal error (all \"end of file\" reached)" in line for line in lines
    )
    has_bibtex_error = has_bibtex_error or any(
        "No file" in line and ".bbl" in line for line in lines
    )

    blg_path = log_path.with_suffix(".blg")
    if blg_path.exists():
        blg_lines = blg_path.read_text(encoding="utf-8", errors="replace").splitlines()
        has_bibtex_error = has_bibtex_error or any(
            "I was expecting a `" in line
            or "---line" in line
            or "Error--" in line and "a `,'" in line
            or "I don't understand this entry" in line
            for line in blg_lines
        )
        has_bibtex_error = has_bibtex_error or any("Fatal error" in line for line in blg_lines)

    return (
        sorted(set(missing_files)),
        sorted(set(missing_commands)),
        has_xelatex_glyph_error,
        sorted(set(glyph_fonts)),
        has_bibtex_error,
    )


def disable_bibliography_in_tex(main_tex: Path) -> bool:
    text = main_tex.read_text(encoding="utf-8", errors="replace")
    changed = False
    pattern = re.compile(
        r"\n\\bibliographystyle\{[^}]+\}\s*\\bibliography\{[^}]+\}\n",
        flags=re.MULTILINE,
    )

    def repl(_match: re.Match[str]) -> str:
        nonlocal changed
        changed = True
        return (
            "\n% Auto fallback: disabled bibtex block due parse error.\n"
            + "\n".join(f"% {line}" for line in _match.group(0).strip().splitlines())
            + "\n"
        )

    new_text = pattern.sub(repl, text)
    if not changed:
        pattern2 = re.compile(
            r"\n\\bibliographystyle\{[^}]+\}\s*\n\\bibliography\{[^}]+\}\n",
            flags=re.MULTILINE,
        )
        new_text = pattern2.sub(repl, new_text)
        changed = new_text != text

    if not changed:
        macro_pattern = re.compile(
            r"^\s*\\bib(?:style|data)\{[^}]+\}\s*$", flags=re.MULTILINE
        )
        changed_lines: list[str] = []
        for line in new_text.splitlines():
            if macro_pattern.match(line):
                changed_lines.append("% " + line)
                changed = True
            else:
                changed_lines.append(line)
        new_text = "\n".join(changed_lines)
        if changed and new_text and not new_text.endswith("\n"):
            new_text += "\n"

    if changed and r"Auto fallback: disabled bibtex block due parse error." not in new_text:
        marker = "% Auto fallback: disabled bibtex block due parse error.\n"
        new_text = marker + new_text
    if changed:
        main_tex.write_text(new_text, encoding="utf-8")
    return changed


def apply_auto_fallbacks_from_log(log_path: Path, zh: Path, main_tex: Path) -> bool:
    (
        missing_files,
        missing_commands,
        has_xelatex_glyph_error,
        _,
        has_bibtex_error,
    ) = parse_latex_failures(log_path)
    changed = False

    if any(item in {"ifsym.sty", "bbm.sty", "bbding.sty"} for item in missing_files):
        normalized = normalize_optional_packages_in_dir(zh)
        if normalized:
            print(f"[build] 已应用缺失可选包兼容补丁：{normalized} 个 TeX 文件", flush=True)
            changed = True

    if has_xelatex_glyph_error:
        normalized = normalize_optional_packages_in_dir(zh)
        if normalized:
            print("[build] 检测到 XeTeXglyph 兼容报错，已为可选编码包添加 XeLaTeX 兼容注释", flush=True)
            changed = True

    if missing_commands:
        if main_tex.exists():
            fallback_injected = inject_missing_command_fallbacks(main_tex, missing_commands)
            if fallback_injected:
                print(f"[build] 已注入未定义命令兼容定义：{', '.join(missing_commands)}", flush=True)
                changed = True
            boundary_fixed = normalize_cjk_adjacent_macros(zh, missing_commands)
            if boundary_fixed:
                print(f"[build] 已修复中文相邻命令边界：{', '.join(missing_commands)}", flush=True)
                changed = True

    if has_bibtex_error:
        if main_tex.exists():
            bib_disabled = disable_bibliography_in_tex(main_tex)
            if bib_disabled:
                print("[build] 已禁用 BibTeX 参考文献块并尝试继续编译", flush=True)
                changed = True

    if not changed and not missing_files and not has_xelatex_glyph_error:
        return False
    if changed:
        return True

    for item in missing_files:
        msg = MISSING_PKG_HINTS.get(item)
        if msg:
            print(f"[build] 该缺失宏包可通过安装补齐（{item}）：{msg}")
    if has_xelatex_glyph_error:
        print(
            "[build] 未检测到可自动修复的 XeTeXglyph 兼容写法；建议检查字体宏包或参考 docs/arxiv_translation.md",
            flush=True,
        )
    return False


def translate_id(args: argparse.Namespace) -> None:
    arxiv_id = normalize_arxiv_id(args.arxiv_id)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_pdf, english_out = ensure_english_pdf(arxiv_id, output_dir, args.force_download)
    zh_out = OUTBOX / f"{arxiv_id}_zh.pdf"

    work = WORK_ROOT / arxiv_id
    should_run_translation = args.dry_run or args.force_translate or args.force_prepare or not zh_out.exists()
    if should_run_translation:
        api_translate(
            argparse.Namespace(
                pdf=str(source_pdf),
                arxiv_id=arxiv_id,
                main=args.main,
                reuse_work=work.exists() and not args.force_prepare,
                force_prepare=args.force_prepare,
                download_source=args.download_source,
                dry_run=args.dry_run,
                main_only=args.main_only,
                force_translate=args.force_translate,
                limit_chunks=args.limit_chunks,
                model=args.model,
                base_url=args.base_url,
                temperature=args.temperature,
                timeout=args.timeout,
                retries=args.retries,
                sleep=args.sleep,
                max_tokens=args.max_tokens,
            )
        )
    else:
        if not args.json:
            print(f"[skip] Chinese PDF already exists: {rel(zh_out)}")

    chinese_out = output_dir / f"{arxiv_id}_zh.pdf"
    if zh_out.exists():
        copy_if_needed(zh_out, chinese_out)
    elif not args.dry_run:
        raise SystemExit(f"中文 PDF 未生成：{zh_out}")

    result = {
        "id": arxiv_id,
        "english_pdf": rel(english_out),
        "chinese_pdf": rel(chinese_out) if chinese_out.exists() else rel(zh_out),
        "dry_run": args.dry_run,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"english-pdf: {result['english_pdf']}")
        print(f"chinese-pdf: {result['chinese_pdf']}")


def build(args: argparse.Namespace) -> None:
    work_id = args.arxiv_id
    work = WORK_ROOT / work_id
    zh = work / "zh"
    tex = zh / args.main
    if not tex.exists():
        raise SystemExit(f"中文 TeX 不存在：{tex}")

    updated = normalize_optional_packages_in_dir(zh)
    if updated:
        print(f"[build] 已补齐可选包兼容写法：{updated} 个 TeX 文件", flush=True)
    build_dir = work / "build_zh"
    print(f"[build] 开始编译: {rel(tex)}", flush=True)
    print(f"[build] 输出目录: {rel(build_dir)}", flush=True)

    max_attempts = 8
    last_exc: subprocess.CalledProcessError | None = None
    for attempt in range(1, max_attempts + 1):
        if build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True, exist_ok=True)

        if attempt > 1:
            print(f"[build] 第 {attempt} 次重试编译: {rel(tex)}", flush=True)

        try:
            run(
                [
                    "latexmk",
                    "-xelatex",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    f"-outdir={build_dir.resolve()}",
                    tex.name,
                ],
                cwd=zh,
            )
            break
        except subprocess.CalledProcessError as exc:
            last_exc = exc
            detail = (exc.stdout or "").strip()
            log_path = build_dir / f"{tex.stem}.log"
            print(f"[build] 中文 PDF 编译失败（第 {attempt} 次）: {detail}", flush=True)

            summarize_latex_failures(log_path)
            if attempt < max_attempts and apply_auto_fallbacks_from_log(log_path, zh, tex):
                print("[build] 已应用可恢复补丁，尝试继续编译", flush=True)
                continue
            break

    if last_exc is not None:
        raise SystemExit("中文 PDF 编译失败")

    pdf = build_dir / f"{tex.stem}.pdf"
    if not pdf.exists():
        raise SystemExit(f"未找到编译产物：{pdf}")
    out_pdf = OUTBOX / f"{work_id}_zh.pdf"
    out_tex = OUTBOX / f"{work_id}_zh.tex"
    shutil.copy2(pdf, out_pdf)
    shutil.copy2(tex, out_tex)
    print(f"[build] 复制产物到: {rel(out_pdf)}", flush=True)
    source_pdf = find_source_pdf(work_id)
    source_side_pdf = None
    if source_pdf is not None:
        source_side_pdf = source_output_path(source_pdf, work_id)
        shutil.copy2(pdf, source_side_pdf)

    meta_path = work / "metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["status"] = "built"
        meta["built_at"] = datetime.now().isoformat(timespec="seconds")
        meta["out_pdf"] = rel(out_pdf)
        meta["out_tex"] = rel(out_tex)
        if source_pdf is not None:
            meta["source_pdf"] = rel(source_pdf)
            meta["source_side_pdf"] = rel(source_side_pdf)
        write_metadata(meta_path, meta)

    print(f"pdf: {rel(out_pdf)}")
    if source_side_pdf is not None:
        print(f"source-folder-pdf: {rel(source_side_pdf)}")
    print(f"tex: {rel(out_tex)}")


def doctor(_: argparse.Namespace) -> None:
    checks = {
        "conda": shutil.which("conda"),
        "python": shutil.which("python"),
        "xelatex": shutil.which("xelatex"),
        "latexmk": shutil.which("latexmk"),
        "pdftotext": shutil.which("pdftotext"),
    }
    for name, path in checks.items():
        print(f"{name}: {path or 'missing'}")

    if shutil.which("kpsewhich"):
        for item in ["ctex.sty", "xeCJK.sty"]:
            try:
                found = run(["kpsewhich", item], capture=True).stdout.strip()
            except subprocess.CalledProcessError:
                found = "missing"
            print(f"{item}: {found or 'missing'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare and build arXiv PDF translation projects.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list project PDFs in translation priority order")
    group = p_list.add_mutually_exclusive_group()
    group.add_argument("--published-only", action="store_true", help="only list papers with publication info")
    group.add_argument("--unpublished-only", action="store_true", help="only list papers under 未查到正式发表信息")
    p_list.add_argument("--json", action="store_true", help="print machine-readable JSON")
    p_list.set_defaults(func=list_papers)

    p_prepare = sub.add_parser("prepare", help="initialize a translation project from an arXiv PDF")
    p_prepare.add_argument("pdf", help="input English arXiv PDF")
    p_prepare.add_argument("--arxiv-id", help="override arXiv ID")
    p_prepare.add_argument("--no-download-source", dest="download_source", action="store_false")
    p_prepare.add_argument("--force", action="store_true", help="overwrite an existing work/<id> directory")
    p_prepare.set_defaults(func=prepare, download_source=True)

    p_prepare_batch = sub.add_parser("prepare-batch", help="initialize many translation projects in priority order")
    batch_group = p_prepare_batch.add_mutually_exclusive_group()
    batch_group.add_argument("--published-only", action="store_true", help="only prepare papers with publication info")
    batch_group.add_argument("--unpublished-only", action="store_true", help="only prepare papers under 未查到正式发表信息")
    p_prepare_batch.add_argument("--include-unpublished", action="store_true", help="include unpublished papers after published papers")
    p_prepare_batch.add_argument("--limit", type=int, help="maximum number of selected PDFs to process")
    p_prepare_batch.add_argument("--no-download-source", dest="download_source", action="store_false")
    p_prepare_batch.add_argument("--force", action="store_true", help="overwrite existing work/<id> directories")
    p_prepare_batch.set_defaults(func=prepare_batch, download_source=True)

    p_api = sub.add_parser("api-translate", help="prepare a PDF, translate with DeepSeek API, and build Chinese PDF")
    p_api.add_argument("pdf", help="input English arXiv PDF")
    p_api.add_argument("--arxiv-id", help="override arXiv ID")
    p_api.add_argument("--main", default="main_zh.tex", help="main Chinese TeX filename under work/<id>/zh")
    p_api.add_argument("--reuse-work", action="store_true", help="reuse existing work/<id> instead of preparing again")
    p_api.add_argument("--force-prepare", action="store_true", help="overwrite existing work/<id> before translating")
    p_api.add_argument("--no-download-source", dest="download_source", action="store_false")
    p_api.add_argument("--dry-run", action="store_true", help="detect chunks without calling DeepSeek or building")
    p_api.add_argument("--main-only", action="store_true", help="only translate --main")
    p_api.add_argument("--force-translate", action="store_true", help="translate chunks even if they already contain Chinese")
    p_api.add_argument("--limit-chunks", type=int, help="translate or preview at most N chunks per file")
    p_api.add_argument("--model", help="DeepSeek model, e.g. deepseek-v4-flash or deepseek-v4-pro")
    p_api.add_argument("--base-url", help="DeepSeek-compatible API base URL")
    p_api.add_argument("--temperature", type=float, help="DeepSeek sampling temperature")
    p_api.add_argument("--timeout", type=int, default=120, help="DeepSeek API timeout seconds (default: 120)")
    p_api.add_argument("--retries", type=int, default=3, help="DeepSeek API retry times (default: 3)")
    p_api.add_argument("--sleep", type=float, default=0.0, help="sleep seconds between API calls")
    p_api.add_argument("--max-tokens", type=int, help="max output tokens for DeepSeek")
    p_api.set_defaults(func=api_translate, download_source=True)

    p_translate_id = sub.add_parser(
        "translate-id",
        help="accept an arXiv ID and output both English PDF and translated Chinese PDF",
    )
    p_translate_id.add_argument("arxiv_id", help="arXiv ID, e.g. 2405.17705 or arXiv URL")
    p_translate_id.add_argument("--output-dir", help="directory for <id>_en.pdf and <id>_zh.pdf; default: workspace outbox")
    p_translate_id.add_argument("--main", default="main_zh.tex", help="main Chinese TeX filename under work/<id>/zh")
    p_translate_id.add_argument("--force-download", action="store_true", help="download English PDF from arXiv even if a local copy exists")
    p_translate_id.add_argument("--force-prepare", action="store_true", help="overwrite existing work/<id> before translating")
    p_translate_id.add_argument("--no-download-source", dest="download_source", action="store_false")
    p_translate_id.add_argument("--dry-run", action="store_true", help="detect chunks without calling DeepSeek or building")
    p_translate_id.add_argument("--main-only", action="store_true", help="only translate --main")
    p_translate_id.add_argument("--force-translate", action="store_true", help="translate chunks even if they already contain Chinese")
    p_translate_id.add_argument("--limit-chunks", type=int, help="translate or preview at most N chunks per file")
    p_translate_id.add_argument("--model", help="DeepSeek model, e.g. deepseek-v4-flash or deepseek-v4-pro")
    p_translate_id.add_argument("--base-url", help="DeepSeek-compatible API base URL")
    p_translate_id.add_argument("--temperature", type=float, help="DeepSeek sampling temperature")
    p_translate_id.add_argument("--timeout", type=int, default=120, help="DeepSeek API timeout seconds (default: 120)")
    p_translate_id.add_argument("--retries", type=int, default=3, help="DeepSeek API retry times (default: 3)")
    p_translate_id.add_argument("--sleep", type=float, default=0.0, help="sleep seconds between API calls")
    p_translate_id.add_argument("--max-tokens", type=int, help="max output tokens for DeepSeek")
    p_translate_id.add_argument("--json", action="store_true", help="print machine-readable paths")
    p_translate_id.set_defaults(func=translate_id, download_source=True)

    p_build = sub.add_parser("build", help="compile translated Chinese TeX to PDF")
    p_build.add_argument("arxiv_id", help="work ID, normally the arXiv ID")
    p_build.add_argument("--main", default="main_zh.tex", help="main Chinese TeX filename under work/<id>/zh")
    p_build.set_defaults(func=build)

    p_doctor = sub.add_parser("doctor", help="check local LaTeX/PDF tools")
    p_doctor.set_defaults(func=doctor)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
