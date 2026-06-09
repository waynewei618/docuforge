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
    p.add_argument(
        "--backend", choices=["deepseek", "claude", "agy"], default="agy",
        help="翻译后端：agy（默认；在 Antigravity 内调 agy -p）/ deepseek（离线终端走 DeepSeek API） / claude（在 Claude Code 内调 claude -p）",
    )
    p.add_argument("--force", action="store_true", help="即使产物已存在也强制重做")

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    opts = PipelineOptions(
        backend=args.backend,
        output_dir=Path(args.output_dir),
        force=args.force,
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
