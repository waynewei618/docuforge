#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


SCRIPT = Path(__file__).resolve()
WORKFLOW_ROOT = SCRIPT.parents[1]
PROJECT_ROOT = SCRIPT.parents[3]
WORKSPACE_ROOT = PROJECT_ROOT / "workspace" / "arxiv_translation"
WORK_ROOT = WORKSPACE_ROOT / "work"
PROMPT_TEMPLATE = WORKFLOW_ROOT / "templates" / "deepseek_system_prompt.md"

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"

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
    "align",
    "align*",
    "acks",
    "algorithm",
    "algorithmic",
    "array",
    "bmatrix",
    "cases",
    "CCSXML",
    "displaymath",
    "equation",
    "equation*",
    "gather",
    "gather*",
    "lstlisting",
    "matrix",
    "multline",
    "multline*",
    "pmatrix",
    "split",
    "tabular",
    "tabular*",
    "tabularx",
    "thebibliography",
    "tikzpicture",
    "verbatim",
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
    dry_run_chunks: int = 0


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def has_cjk(text: str) -> bool:
    return re.search(r"[\u3400-\u9fff]", text) is not None


def cjk_ratio(text: str) -> float:
    visible = [ch for ch in text if not ch.isspace()]
    if not visible:
        return 0.0
    cjk = sum(1 for ch in visible if "\u3400" <= ch <= "\u9fff")
    return cjk / len(visible)


def has_english_letters(text: str) -> bool:
    return re.search(r"[A-Za-z]{3,}", text) is not None


def visible_words(text: str) -> str:
    text = re.sub(r"\\[A-Za-z@]+\*?", " ", text)
    text = re.sub(r"[$^_{}[\]~&%#]", " ", text)
    return text


def should_translate(text: str, force: bool) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if not force and has_cjk(stripped):
        return False
    if not has_english_letters(visible_words(stripped)):
        return False
    return True


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def unwrap_text_command(text: str) -> str:
    stripped = strip_code_fence(text)
    pattern = re.compile(
        r"^\\(" + "|".join(sorted(TEXT_COMMANDS, key=len, reverse=True)) + r")\*?(?:\[[^\]]*\])?\{",
        re.DOTALL,
    )
    match = pattern.match(stripped)
    if not match:
        return stripped
    arg = find_balanced_argument(stripped, match.end() - 1)
    if arg is None:
        return stripped
    start, end = arg
    if stripped[end + 1 :].strip():
        return stripped
    return stripped[start:end].strip()


def env_name_from_line(line: str, command: str) -> str | None:
    match = re.search(rf"\\{command}\{{([^}}]+)\}}", line)
    return match.group(1) if match else None


def is_pure_latex_line(line: str) -> bool:
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


def find_balanced_argument(text: str, open_brace: int) -> tuple[int, int] | None:
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


def command_arg_chunks(text: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    pattern = re.compile(r"\\(" + "|".join(sorted(TEXT_COMMANDS, key=len, reverse=True)) + r")\*?(?:\[[^\]]*\])?\{")
    for match in pattern.finditer(text):
        arg = find_balanced_argument(text, match.end() - 1)
        if arg is None:
            continue
        start, end = arg
        body = text[start:end]
        if "\n\n" in body:
            continue
        chunks.append(Chunk(start=start, end=end, text=body, kind=match.group(1)))
    return chunks


def paragraph_chunks(text: str, occupied: list[tuple[int, int]]) -> list[Chunk]:
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

        begin = env_name_from_line(line, "begin")
        if begin in PROTECTED_ENVS:
            flush(line_start)
            env_stack.append(begin)

        end = env_name_from_line(line, "end")
        in_protected_env = bool(env_stack)
        line_is_occupied = overlaps(line_start, line_end)

        if not in_document or in_protected_env or line_is_occupied or is_pure_latex_line(line):
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
    command_chunks = command_arg_chunks(text)
    occupied = [(chunk.start, chunk.end) for chunk in command_chunks]
    chunks = command_chunks + paragraph_chunks(text, occupied)
    chunks.sort(key=lambda chunk: (chunk.start, chunk.end))
    filtered: list[Chunk] = []
    last_end = -1
    for chunk in chunks:
        if chunk.start < last_end:
            continue
        filtered.append(chunk)
        last_end = chunk.end
    return filtered


class DeepSeekClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float,
        max_tokens: int | None,
        timeout: int,
        retries: int,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.retries = retries

    def translate(self, system_prompt: str, text: str) -> str:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": self.temperature,
            "stream": False,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8")
                parsed = json.loads(body)
                return strip_code_fence(parsed["choices"][0]["message"]["content"])
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                wait = min(30, 2**attempt)
                print(f"[warn] DeepSeek 请求失败，{wait}s 后重试：{exc}", flush=True)
                time.sleep(wait)

        raise RuntimeError(f"DeepSeek 请求失败：{last_error}")


def load_system_prompt(work: Path) -> str:
    if PROMPT_TEMPLATE.exists():
        prompt = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    else:
        prompt = "把英文 LaTeX 论文片段翻译为中文，保留所有 LaTeX 结构。"

    rules = work / "notes" / "translation_rules.md"
    if rules.exists():
        prompt += "\n\n# 本论文翻译规则\n\n"
        prompt += rules.read_text(encoding="utf-8")
    return prompt


def discover_tex_files(work: Path, args: argparse.Namespace) -> list[Path]:
    zh = work / "zh"
    if args.files:
        files = [(zh / item).resolve() for item in args.files]
    elif args.main_only:
        files = [zh / args.main]
    else:
        files = []
        for path in sorted(zh.rglob("*.tex")):
            if SKIP_FILE_RE.search(path.name) or SKIP_TEX_NAME_RE.search(path.stem):
                continue
            if path.name != args.main:
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


def append_log(work: Path, row: dict[str, object]) -> None:
    log_path = work / "notes" / "deepseek_translation_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def backup_file(path: Path, zh_root: Path, backup_root: Path) -> None:
    target = backup_root / path.relative_to(zh_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def translate_file(
    path: Path,
    work: Path,
    client: DeepSeekClient | None,
    system_prompt: str,
    args: argparse.Namespace,
    stats: Stats,
) -> None:
    original = path.read_text(encoding="utf-8", errors="replace")
    chunks = [chunk for chunk in collect_chunks(original) if should_translate(chunk.text, args.force)]
    stats.chunks += len(chunks)

    if args.dry_run:
        print(f"[dry-run] {rel(path)}: {len(chunks)} chunks", flush=True)
        for chunk in chunks[: args.limit_chunks or len(chunks)]:
            preview = re.sub(r"\s+", " ", chunk.text.strip())[:140]
            print(f"  - {chunk.kind}: {preview}", flush=True)
        stats.dry_run_chunks += len(chunks)
        return

    if not chunks:
        print(f"[skip] {rel(path)}: no English chunks", flush=True)
        return

    translated_parts: list[str] = []
    cursor = 0
    changed = False
    processed = 0
    limit = args.limit_chunks

    for index, chunk in enumerate(chunks, start=1):
        translated_parts.append(original[cursor : chunk.start])
        if limit is not None and processed >= limit:
            translated_parts.append(chunk.text)
            cursor = chunk.end
            stats.skipped += 1
            continue

        assert client is not None
        print(f"[translate] {rel(path)} chunk {index}/{len(chunks)} ({chunk.kind}, {len(chunk.text)} chars)", flush=True)
        before_hash = sha256(chunk.text)
        output = client.translate(system_prompt, chunk.text)
        if chunk.kind in TEXT_COMMANDS:
            output = unwrap_text_command(output)
        if not output:
            output = chunk.text
        translated_parts.append(output)
        cursor = chunk.end
        changed = changed or output != chunk.text
        processed += 1
        stats.translated += 1
        append_log(
            work,
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "file": rel(path),
                "chunk": index,
                "kind": chunk.kind,
                "input_sha256": before_hash,
                "output_sha256": sha256(output),
                "input_chars": len(chunk.text),
                "output_chars": len(output),
                "model": args.model,
            },
        )
        if args.sleep > 0:
            time.sleep(args.sleep)

    translated_parts.append(original[cursor:])
    if changed:
        backup_file(path, work / "zh", work / "api_backups" / args.backup_stamp)
        path.write_text("".join(translated_parts), encoding="utf-8")
        print(f"[write] {rel(path)}", flush=True)


def run_build(work_id: str, main: str) -> None:
    subprocess.run(
        [
            "python",
            str(WORKFLOW_ROOT / "scripts" / "translate_arxiv_pdf.py"),
            "build",
            work_id,
            "--main",
            main,
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )


def translate(args: argparse.Namespace) -> None:
    work = WORK_ROOT / args.arxiv_id
    if not work.exists():
        raise SystemExit(f"工作目录不存在：{work}")

    files = discover_tex_files(work, args)
    if args.list_files:
        for path in files:
            print(rel(path), flush=True)
        return

    stats = Stats(files=len(files))
    client: DeepSeekClient | None = None
    system_prompt = load_system_prompt(work)

    if not args.dry_run:
        api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise SystemExit("缺少 DEEPSEEK_API_KEY。请先 export DEEPSEEK_API_KEY='sk-...'。")
        client = DeepSeekClient(
            api_key=api_key,
            base_url=args.base_url,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            retries=args.retries,
        )

    for path in files:
        translate_file(path, work, client, system_prompt, args, stats)

    print(
        "summary: "
        f"files={stats.files} chunks={stats.chunks} translated={stats.translated} "
        f"skipped={stats.skipped} dry_run_chunks={stats.dry_run_chunks}",
        flush=True,
    )

    if args.build and not args.dry_run:
        run_build(args.arxiv_id, args.main)


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate prepared arXiv LaTeX projects with DeepSeek API.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_translate = sub.add_parser("translate", help="translate work/<id>/zh TeX files in place")
    p_translate.add_argument("arxiv_id", help="work ID, normally the arXiv ID")
    p_translate.add_argument("--main", default="main_zh.tex", help="main Chinese TeX filename")
    p_translate.add_argument("--main-only", action="store_true", help="only translate --main")
    p_translate.add_argument("--files", nargs="+", help="specific TeX files relative to work/<id>/zh")
    p_translate.add_argument("--list-files", action="store_true", help="list target TeX files and exit")
    p_translate.add_argument("--dry-run", action="store_true", help="show detected chunks without calling DeepSeek")
    p_translate.add_argument("--limit-chunks", type=int, help="translate or preview at most N chunks per file")
    p_translate.add_argument("--force", action="store_true", help="translate chunks even if they already contain Chinese")
    p_translate.add_argument("--build", action="store_true", help="compile PDF after translation")
    p_translate.add_argument("--api-key", help="DeepSeek API key; prefer DEEPSEEK_API_KEY env var")
    p_translate.add_argument("--base-url", default=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL))
    p_translate.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL))
    p_translate.add_argument("--temperature", type=float, default=float(os.environ.get("DEEPSEEK_TEMPERATURE", "0.2")))
    p_translate.add_argument("--max-tokens", type=int, default=None)
    p_translate.add_argument("--timeout", type=int, default=120)
    p_translate.add_argument("--retries", type=int, default=3)
    p_translate.add_argument("--sleep", type=float, default=0.0, help="seconds to sleep between API calls")
    p_translate.set_defaults(
        func=translate,
        backup_stamp=datetime.now().strftime("%Y%m%d-%H%M%S"),
    )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
