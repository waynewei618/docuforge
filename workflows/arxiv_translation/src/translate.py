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
    p.add_argument("--main", default="main_zh.tex", help="中文主 TeX 文件名")
    p.add_argument("--force", action="store_true", help="即使产物已存在也强制重做")
    p.add_argument("--limit-chunks", type=int, help="每文件至多翻译 N 个 chunk（调试用）")
    p.add_argument("--main-only", action="store_true", help="只翻译 --main 一个文件")
    p.add_argument("--no-source", action="store_true", help="不下载 arXiv e-print 源码")
    p.add_argument("--json", action="store_true", dest="json_out", help="机器可读输出")

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    opts = PipelineOptions(
        backend=args.backend,
        output_dir=Path(args.output_dir),
        main=args.main,
        force=args.force,
        limit_chunks=args.limit_chunks,
        main_only=args.main_only,
        no_source=args.no_source,
    )

    result = run_pipeline(args.input, opts)

    payload = {
        "id": result.arxiv_id,
        "english_pdf": str(result.english_pdf) if result.english_pdf else None,
        "chinese_pdf": str(result.chinese_pdf) if result.chinese_pdf else None,
        "skipped": result.skipped,
        "work_dir": str(result.work_dir) if result.work_dir else None,
    }
    if args.json_out:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"english-pdf: {payload['english_pdf']}")
        print(f"chinese-pdf: {payload['chinese_pdf']}")
        if result.work_dir:
            print(f"debug-cache: {payload['work_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
