"""CLI 入口：python -m src.translate <input> [选项]。

<input>: arXiv ID（2405.17705 / 带版本 / URL）或本地 PDF 路径。
默认产物落在 workflows/arxiv_translation/output/<id>_{en,zh}.pdf。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .backends import DEFAULT_DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_MODEL
from .pipeline import OUTPUT_DEFAULT, PipelineOptions, run_pipeline


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="src.translate",
        description="把 arXiv 论文翻译为中文 PDF。输入可为 arXiv ID / URL / 本地 PDF。",
    )
    p.add_argument("input", help="arXiv ID（2405.17705 / 带 v2 / arXiv URL）或本地 PDF 路径")
    p.add_argument(
        "--output-dir", default=str(OUTPUT_DEFAULT),
        help=f"产物目录，默认 {OUTPUT_DEFAULT}",
    )
    p.add_argument("--force", action="store_true", help="即使产物已存在也强制重做")
    p.add_argument("--prepare", action="store_true", help="【Agent 异步协作模式】仅解包 LaTeX 并导出待翻译的 JSON 文本")
    p.add_argument("--compile", action="store_true", help="【Agent 异步协作模式】仅读取已翻译好的 JSON 写回并编译 PDF")

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.prepare and args.compile:
        print("[error] 参数冲突：--prepare 与 --compile 不能同时使用", file=sys.stderr)
        return 1

    opts = PipelineOptions(
        output_dir=Path(args.output_dir),
        force=args.force,
        prepare_only=args.prepare,
        compile_only=args.compile,
    )

    result = run_pipeline(args.input, opts)

    english_pdf = str(result.english_pdf) if result.english_pdf else None
    chinese_pdf = str(result.chinese_pdf) if result.chinese_pdf else None

    print(f"english-pdf: {english_pdf}")
    print(f"chinese-pdf: {chinese_pdf}")
    if result.work_dir:
        print(f"debug-cache: {result.work_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
