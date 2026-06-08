"""TeX 翻译循环：chunk 切分 / 文件遍历 / 备份 / 调 backend。

由 pipeline.run_pipeline() 直接以函数形式调用，不再 subprocess。
backend 实例由调用方传入（DeepSeek / Claude Code）。
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .backends import TranslationBackend


TEXT_COMMANDS = {
    "title",
    "section",
    "subsection",
    "subsubsection",
    "paragraph",
    "subparagraph",
    "caption",
}

PROTECTED_ENVS = {
    "align", "align*", "acks", "algorithm", "algorithmic", "array", "bmatrix",
    "cases", "CCSXML", "displaymath", "equation", "equation*", "gather",
    "gather*", "lstlisting", "matrix", "multline", "multline*", "pmatrix",
    "split", "tabular", "tabular*", "tabularx", "thebibliography",
    "tikzpicture", "verbatim",
}

SKIP_FILE_RE = re.compile(
    r"(\.bbl$|\.bib$|\.cls$|\.sty$|\.bst$|\.aux$|\.out$|\.log$|\.fls$|\.fdb_latexmk$)"
)
SKIP_TEX_NAME_RE = re.compile(r"(conference|template|style|macros?|commands?|defs?)", re.IGNORECASE)


@dataclass
class Chunk:
    start: int
    end: int
    text: str
    kind: str


@dataclass
class Stats:
    files: int = 0
    chunks: int = 0
    translated: int = 0
    skipped: int = 0


@dataclass
class TranslateOptions:
    """传给 translate_work 的所有可调参数。"""
    main: str = "main_zh.tex"
    main_only: bool = False
    files: list[str] = field(default_factory=list)
    limit_chunks: int | None = None
    force: bool = False
    sleep: float = 0.0
    backup_stamp: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d-%H%M%S"))


# ---------- 文本辅助 ----------

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _has_cjk(text: str) -> bool:
    return re.search(r"[\u3400-\u9fff]", text) is not None


def _has_english_letters(text: str) -> bool:
    return re.search(r"[A-Za-z]{3,}", text) is not None


def _visible_words(text: str) -> str:
    text = re.sub(r"\\[A-Za-z@]+\*?", " ", text)
    text = re.sub(r"[$^_{}[\]~&%#]", " ", text)
    return text


def _should_translate(text: str, force: bool) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if not force and _has_cjk(stripped):
        return False
    if not _has_english_letters(_visible_words(stripped)):
        return False
    return True


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _unwrap_text_command(text: str) -> str:
    stripped = _strip_code_fence(text)
    pattern = re.compile(
        r"^\\(" + "|".join(sorted(TEXT_COMMANDS, key=len, reverse=True)) + r")\*?(?:\[[^\]]*\])?\{",
        re.DOTALL,
    )
    match = pattern.match(stripped)
    if not match:
        return stripped
    arg = _find_balanced_argument(stripped, match.end() - 1)
    if arg is None:
        return stripped
    start, end = arg
    if stripped[end + 1:].strip():
        return stripped
    return stripped[start:end].strip()


def _env_name_from_line(line: str, command: str) -> str | None:
    match = re.search(rf"\\{command}\{{([^}}]+)\}}", line)
    return match.group(1) if match else None


def _is_pure_latex_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("%"):
        return True
    if stripped.startswith("\\") and not re.match(
        r"\\(item\b|noindent\b|textbf\{|emph\{|textit\{|texttt\{)", stripped
    ):
        return True
    if stripped in {"{", "}", "\\\\"}:
        return True
    return False


def _find_balanced_argument(text: str, open_brace: int) -> tuple[int, int] | None:
    depth = 0
    escaped = False
    for index in range(open_brace, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return open_brace + 1, index
    return None


def _command_arg_chunks(text: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    pattern = re.compile(r"\\(" + "|".join(sorted(TEXT_COMMANDS, key=len, reverse=True)) + r")\*?(?:\[[^\]]*\])?\{")
    for match in pattern.finditer(text):
        arg = _find_balanced_argument(text, match.end() - 1)
        if arg is None:
            continue
        start, end = arg
        body = text[start:end]
        if "\n\n" in body:
            continue
        chunks.append(Chunk(start=start, end=end, text=body, kind=match.group(1)))
    return chunks


def _paragraph_chunks(text: str, occupied: list[tuple[int, int]]) -> list[Chunk]:
    lines = text.splitlines(keepends=True)
    chunks: list[Chunk] = []
    env_stack: list[str] = []
    buffer: list[str] = []
    buffer_start: int | None = None
    offset = 0
    has_document_env = r"\begin{document}" in text
    in_document = not has_document_env

    def overlaps(start: int, end: int) -> bool:
        return any(start < item_end and end > item_start for item_start, item_end in occupied)

    def flush(end_offset: int) -> None:
        nonlocal buffer, buffer_start
        if buffer and buffer_start is not None:
            chunk_text = "".join(buffer)
            chunks.append(Chunk(start=buffer_start, end=end_offset, text=chunk_text, kind="paragraph"))
        buffer = []
        buffer_start = None

    for line in lines:
        line_start = offset
        line_end = offset + len(line)
        stripped = line.strip()

        if r"\begin{document}" in line:
            in_document = True
            flush(line_start)
            offset = line_end
            continue

        begin = _env_name_from_line(line, "begin")
        if begin in PROTECTED_ENVS:
            flush(line_start)
            env_stack.append(begin)

        end = _env_name_from_line(line, "end")
        in_protected_env = bool(env_stack)
        line_is_occupied = overlaps(line_start, line_end)

        if not in_document or in_protected_env or line_is_occupied or _is_pure_latex_line(line):
            flush(line_start)
        elif stripped == "":
            flush(line_start)
        else:
            if buffer_start is None:
                buffer_start = line_start
            buffer.append(line)

        if end in PROTECTED_ENVS and env_stack:
            if end in env_stack:
                while env_stack:
                    popped = env_stack.pop()
                    if popped == end:
                        break
            else:
                env_stack.pop()

        offset = line_end

    flush(len(text))
    return chunks


def collect_chunks(text: str) -> list[Chunk]:
    command_chunks = _command_arg_chunks(text)
    occupied = [(chunk.start, chunk.end) for chunk in command_chunks]
    chunks = command_chunks + _paragraph_chunks(text, occupied)
    chunks.sort(key=lambda chunk: (chunk.start, chunk.end))
    filtered: list[Chunk] = []
    last_end = -1
    for chunk in chunks:
        if chunk.start < last_end:
            continue
        filtered.append(chunk)
        last_end = chunk.end
    return filtered


# ---------- 文件发现 / 备份 / 日志 ----------

def _discover_tex_files(work: Path, opts: TranslateOptions) -> list[Path]:
    zh = work / "zh"
    if opts.files:
        files = [(zh / item).resolve() for item in opts.files]
    elif opts.main_only:
        files = [zh / opts.main]
    else:
        files = []
        for path in sorted(zh.rglob("*.tex")):
            if SKIP_FILE_RE.search(path.name) or SKIP_TEX_NAME_RE.search(path.stem):
                continue
            if path.name != opts.main:
                head = path.read_text(encoding="utf-8", errors="replace")[:5000]
                if r"\documentclass" in head:
                    continue
            files.append(path)

    clean: list[Path] = []
    for path in files:
        if not path.exists():
            raise SystemExit(f"TeX 文件不存在：{path}")
        try:
            path.resolve().relative_to(zh.resolve())
        except ValueError as exc:
            raise SystemExit(f"文件不在 zh 目录下：{path}") from exc
        clean.append(path)
    return clean


def _append_log(work: Path, row: dict[str, object]) -> None:
    log_path = work / "notes" / "deepseek_translation_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _backup_file(path: Path, zh_root: Path, backup_root: Path) -> None:
    target = backup_root / path.relative_to(zh_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def _rel(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def _load_system_prompt(work: Path, templates_dir: Path) -> str:
    prompt_template = templates_dir / "deepseek_system_prompt.md"
    if prompt_template.exists():
        prompt = prompt_template.read_text(encoding="utf-8")
    else:
        prompt = "把英文 LaTeX 论文片段翻译为中文，保留所有 LaTeX 结构。"
    rules = work / "notes" / "translation_rules.md"
    if rules.exists():
        prompt += "\n\n# 本论文翻译规则\n\n" + rules.read_text(encoding="utf-8")
    return prompt


# ---------- 单文件翻译 ----------

def _translate_file(
    path: Path,
    work: Path,
    backend: TranslationBackend,
    system_prompt: str,
    opts: TranslateOptions,
    stats: Stats,
    project_root: Path,
    backend_model: str,
) -> None:
    original = path.read_text(encoding="utf-8", errors="replace")
    chunks = [chunk for chunk in collect_chunks(original) if _should_translate(chunk.text, opts.force)]
    stats.chunks += len(chunks)

    if not chunks:
        print(f"[skip] {_rel(path, project_root)}: no English chunks", flush=True)
        return

    translated_parts: list[str] = []
    cursor = 0
    changed = False
    processed = 0
    limit = opts.limit_chunks

    for index, chunk in enumerate(chunks, start=1):
        translated_parts.append(original[cursor:chunk.start])
        if limit is not None and processed >= limit:
            translated_parts.append(chunk.text)
            cursor = chunk.end
            stats.skipped += 1
            continue

        print(
            f"[translate] {_rel(path, project_root)} chunk {index}/{len(chunks)} "
            f"({chunk.kind}, {len(chunk.text)} chars)",
            flush=True,
        )
        before_hash = _sha256(chunk.text)
        output = backend.translate(system_prompt, chunk.text)
        if chunk.kind in TEXT_COMMANDS:
            output = _unwrap_text_command(output)
        if not output:
            output = chunk.text
        translated_parts.append(output)
        cursor = chunk.end
        changed = changed or output != chunk.text
        processed += 1
        stats.translated += 1
        _append_log(
            work,
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "file": _rel(path, project_root),
                "chunk": index,
                "kind": chunk.kind,
                "input_sha256": before_hash,
                "output_sha256": _sha256(output),
                "input_chars": len(chunk.text),
                "output_chars": len(output),
                "model": backend_model,
            },
        )
        if opts.sleep > 0:
            time.sleep(opts.sleep)

    translated_parts.append(original[cursor:])
    if changed:
        _backup_file(path, work / "zh", work / "api_backups" / opts.backup_stamp)
        path.write_text("".join(translated_parts), encoding="utf-8")
        print(f"[write] {_rel(path, project_root)}", flush=True)


# ---------- 公共入口 ----------

def translate_work(
    work: Path,
    backend: TranslationBackend,
    opts: TranslateOptions,
    templates_dir: Path,
    project_root: Path,
    backend_model: str = "",
) -> Stats:
    """对 work/<id>/zh/ 下的 TeX 做翻译。"""
    if not work.exists():
        raise SystemExit(f"工作目录不存在：{work}")

    files = _discover_tex_files(work, opts)
    stats = Stats(files=len(files))
    system_prompt = _load_system_prompt(work, templates_dir)

    for path in files:
        _translate_file(path, work, backend, system_prompt, opts, stats, project_root, backend_model)

    print(
        "summary: "
        f"files={stats.files} chunks={stats.chunks} translated={stats.translated} "
        f"skipped={stats.skipped}",
        flush=True,
    )
    return stats
