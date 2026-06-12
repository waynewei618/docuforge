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
        
    if stripped.startswith("\\"):
        if re.match(r"^\s*\\(?:includegraphics|label|input|vspace|hspace|centering|bibliographystyle|bibliography|url)\b", stripped):
            return True
        if not _has_english_letters(_visible_words(stripped)):
            return True
        return False

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
        elif re.match(r"^\s*\\(?:boldparagraph|noindent|paragraph|item|subparagraph)\b", line):
            flush(line_start)
            if buffer_start is None:
                buffer_start = line_start
            buffer.append(line)
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

    _backup_file(path, work / "zh", work / "api_backups" / opts.backup_stamp)

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

        if changed:
            temp_path = path.with_name(path.name + ".tmp")
            temp_path.write_text("".join(translated_parts) + original[cursor:], encoding="utf-8")
            temp_path.replace(path)

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
        temp_path = path.with_name(path.name + ".tmp")
        temp_path.write_text("".join(translated_parts), encoding="utf-8")
        temp_path.replace(path)
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


def export_chunks_to_json(work: Path, opts: TranslateOptions, project_root: Path) -> Path:
    """遍历待翻译 TeX 文件，将待翻译 chunk 导出为 chunks_to_translate.json。"""
    files = _discover_tex_files(work, opts)
    all_chunks_data = []

    for path in files:
        original = path.read_text(encoding="utf-8", errors="replace")
        chunks = collect_chunks(original)
        rel_file = _rel(path, work / "zh")

        for index, chunk in enumerate(chunks, start=1):
            if _should_translate(chunk.text, opts.force):
                all_chunks_data.append({
                    "chunk_id": f"{rel_file}_{index}",
                    "file": rel_file,  # 相对 zh 目录的路径
                    "index": index,
                    "start": chunk.start,
                    "end": chunk.end,
                    "kind": chunk.kind,
                    "source_sha256": _sha256(chunk.text),
                    "text": chunk.text,
                    "status": "pending",
                    "translated": None
                })

    out_path = work / "notes" / "chunks_to_translate.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_chunks_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] 已成功导出待翻译 chunks 至: {_rel(out_path, project_root)}", flush=True)
    return out_path


def import_chunks_from_json(work: Path) -> int:
    """读取已翻译的 chunks 并逆向替换写入 zh/ 下对应的 TeX 文件。"""
    in_path = work / "notes" / "chunks_translated.json"
    if not in_path.exists():
        print(f"[warn] 未找到 chunks_translated.json，跳过导入", flush=True)
        return 0

    try:
        data = json.loads(in_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[error] 读取或解析 JSON 失败: {exc}", flush=True)
        return 0

    # 按文件分组
    by_file: dict[str, list[dict[str, object]]] = {}
    for item in data:
        file_name = item.get("file")
        if file_name and isinstance(file_name, str):
            by_file.setdefault(file_name, []).append(item)

    updated_files = 0
    backup_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    for rel_file, items in by_file.items():
        file_path = work / "zh" / rel_file
        if not file_path.exists():
            print(f"[warn] 要写回的文件不存在: {file_path}", flush=True)
            continue

        original = file_path.read_text(encoding="utf-8", errors="replace")

        # 按照 start 从大到小排序，从文件后部逆向替换，避免替换后字符长度变化引起前文索引偏移
        valid_items = []
        for item in items:
            start = item.get("start")
            end = item.get("end")
            if isinstance(start, int) and isinstance(end, int):
                valid_items.append(item)

        valid_items.sort(key=lambda x: x["start"], reverse=True)

        parts = []
        cursor = len(original)
        changed = False

        for item in valid_items:
            translated = item.get("translated")
            start = item["start"]
            end = item["end"]
            text_val = item.get("text", "")
            source_sha256 = item.get("source_sha256", "")
            status = item.get("status", "")

            # 仅当 status 为 translated 且 translated 存在且非空时替换
            if status == "translated" and isinstance(translated, str) and translated.strip():
                # 校验 1: 索引段的原文内容是否匹配
                if original[start:end] != text_val:
                    print(f"[warn] {rel_file} 中的 chunk (start={start}) 文本不匹配，跳过写回以免破坏文件。", flush=True)
                    parts.append(original[end:cursor])
                    parts.append(original[start:end])
                    cursor = start
                    continue

                # 校验 2: 校验哈希值是否匹配
                current_sha256 = _sha256(original[start:end])
                if current_sha256 != source_sha256:
                    print(f"[warn] {rel_file} 中的 chunk (start={start}) SHA256 哈希值不匹配 (expected={source_sha256}, got={current_sha256})，跳过写回以免破坏文件。", flush=True)
                    parts.append(original[end:cursor])
                    parts.append(original[start:end])
                    cursor = start
                    continue

                # 提取 text command 的内容规范化（如果是 text command）
                kind = item.get("kind", "paragraph")
                if kind in TEXT_COMMANDS:
                    translated = _unwrap_text_command(translated)

                # 保持原文的末尾换行符，防止不同段落合并
                if text_val.endswith("\n") and not translated.endswith("\n"):
                    translated += "\n"

                parts.append(original[end:cursor])
                parts.append(translated)
                cursor = start
                changed = True
            else:
                # 保持原样
                parts.append(original[end:cursor])
                parts.append(text_val if isinstance(text_val, str) else "")
                cursor = start

        parts.append(original[:cursor])
        parts.reverse()

        if changed:
            _backup_file(file_path, work / "zh", work / "api_backups" / backup_stamp)
            file_path.write_text("".join(parts), encoding="utf-8")
            print(f"[import] 已成功写回翻译内容: {rel_file}", flush=True)
            updated_files += 1

    return updated_files


