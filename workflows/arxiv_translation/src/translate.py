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

    g_llm = p.add_argument_group("大模型与翻译控制（通用）")
    g_llm.add_argument("--model", help="大模型名称。如不指定，agy/claude 路由至默认环境变量，deepseek 默认为 deepseek-v4-flash")
    g_llm.add_argument("--timeout", type=int, help="单次请求超时时间（秒）。默认：deepseek 120, claude/agy 300")
    g_llm.add_argument("--retries", type=int, help="失败重试次数。默认：deepseek 3, claude/agy 2")

    g_api = p.add_argument_group("API 专属选项（一般仅在 API 类后端生效）")
    g_api.add_argument("--api-key", help="API 秘钥。对 deepseek 优先读取 DEEPSEEK_API_KEY 环境变量")
    g_api.add_argument("--base-url", help="API base URL。对 deepseek 默认为 https://api.deepseek.com")
    g_api.add_argument("--temperature", type=float, default=0.2, help="大模型采样温度，默认 0.2")
    g_api.add_argument("--max-tokens", type=int, help="限制单次响应的最大 token 数")
    g_api.add_argument("--sleep", type=float, default=0.0, help="单次翻译请求后的延迟休眠时间（秒），默认 0.0")

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
        model=args.model,
        timeout=args.timeout,
        retries=args.retries,
        api_key=args.api_key,
        base_url=args.base_url,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        sleep=args.sleep,
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
