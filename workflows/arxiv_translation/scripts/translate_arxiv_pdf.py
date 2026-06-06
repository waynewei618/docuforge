#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
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


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )


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
    return pattern.sub(lambda match: match.group(1) + "\n" + cjk, tex, count=1)


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
    block_re = re.compile(
        r"\{\s*\\bibliographystyle\{[^}]+\}\s*\\bibliography\{[^}]+\}\s*\}",
        flags=re.DOTALL,
    )
    if block_re.search(tex):
        return block_re.sub(replacement, tex, count=1)

    return re.sub(
        r"\\bibliographystyle\{[^}]+\}\s*\\bibliography\{[^}]+\}",
        replacement,
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
                    "--fail",
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
            print(f"[warn] arXiv 源码 curl 下载失败：{exc.stdout.strip()}")
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
                    "--fail",
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
            print(f"[warn] arXiv PDF curl 下载失败：{exc.stdout.strip()}")
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
        print(exc.stdout)
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
    work = WORK_ROOT / work_id
    if work.exists() and not args.force:
        raise SystemExit(f"工作目录已存在，拒绝覆盖：{work}\n如需重建，请显式添加 --force。")
    if work.exists() and args.force:
        shutil.rmtree(work)

    notes = work / "notes"
    source = work / "source"
    zh = work / "zh"
    for path in [INBOX, OUTBOX, work, notes, zh]:
        path.mkdir(parents=True, exist_ok=True)

    inbox_pdf = INBOX / pdf.name
    work_pdf = work / "input.pdf"
    if pdf.resolve() != inbox_pdf.resolve():
        shutil.copy2(pdf, inbox_pdf)
    shutil.copy2(pdf, work_pdf)

    source_status = "not_requested"
    archive = work / "e-print.tar.gz"
    main_tex: Path | None = None
    if args.download_source and re.fullmatch(r"\d{4}\.\d{4,5}", work_id):
        if download_arxiv_source(work_id, archive):
            extract_source_archive(archive, source)
            source_status = "downloaded"
            main_tex = find_main_tex(source)
        else:
            source_status = "download_failed"

    extracted_txt = work / "extracted.txt"
    extracted = False
    if main_tex is None:
        extracted = extract_pdf_text(work_pdf, extracted_txt)

    if main_tex is not None:
        copy_source_tree(source, zh)
        zh_main = zh / "main_zh.tex"
        seed = main_tex.read_text(encoding="utf-8", errors="replace")
        seed = use_existing_bbl_when_bib_missing(seed, source, main_tex)
        zh_main.write_text(inject_chinese_preamble(seed), encoding="utf-8")
    else:
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

    print(f"prepared: {rel(work)}")
    print(f"translate: {rel(zh_main)}")
    print(f"rules: {rel(notes / 'translation_rules.md')}")


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
    if work.exists():
        if not args.reuse_work and not args.force_prepare:
            raise SystemExit(
                f"工作目录已存在：{work}\n"
                "如需沿用现有工作目录，请添加 --reuse-work；如需重建，请添加 --force-prepare。"
            )
        if args.force_prepare:
            prepare(
                argparse.Namespace(
                    pdf=str(pdf),
                    arxiv_id=args.arxiv_id,
                    download_source=args.download_source,
                    force=True,
                )
            )
    else:
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
    if args.model:
        cmd.extend(["--model", args.model])
    if args.base_url:
        cmd.extend(["--base-url", args.base_url])
    if args.temperature is not None:
        cmd.extend(["--temperature", str(args.temperature)])

    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)


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
    build_dir = work / "build_zh"
    build_dir.mkdir(parents=True, exist_ok=True)

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
    except subprocess.CalledProcessError as exc:
        print(exc.stdout)
        raise SystemExit("中文 PDF 编译失败")

    pdf = build_dir / f"{tex.stem}.pdf"
    if not pdf.exists():
        raise SystemExit(f"未找到编译产物：{pdf}")
    out_pdf = OUTBOX / f"{work_id}_zh.pdf"
    out_tex = OUTBOX / f"{work_id}_zh.tex"
    shutil.copy2(pdf, out_pdf)
    shutil.copy2(tex, out_tex)
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
                found = run(["kpsewhich", item]).stdout.strip()
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
