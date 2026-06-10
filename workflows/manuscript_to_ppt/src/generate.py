"""CLI 入口：python -m src.generate <image_path> [选项]。

三段式工作流（与 arxiv_translation 对齐）：

1. --prepare  : 创建工作目录，准备元数据，等待 Agent 生成 frames.tex
2. (Agent)    : Agent 读取手稿图片，用自身 Vision LLM 生成 Beamer frame 代码，
                写入 tmp/work/<id>/frames.tex
3. --compile  : 拼接 preamble + frames，调用 latexmk 编译，输出到 outputs/
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .compile import CompileResult, clean_aux, compile_tex, pdf_to_png

# 路径约定
_WORKFLOW_ROOT = Path(__file__).resolve().parent.parent  # workflows/manuscript_to_ppt
_PROJECT_ROOT = _WORKFLOW_ROOT.parent.parent              # 项目根目录
_TEMPLATES_DIR = _WORKFLOW_ROOT / "templates"
_TMP_DIR = _WORKFLOW_ROOT / "tmp"
_OUTPUT_DEFAULT = _PROJECT_ROOT / "outputs" / "manuscript_to_ppt"


def _image_id(image_path: Path) -> str:
    """从图片路径生成工作 ID（去掉扩展名，保留文件名）。"""
    return image_path.stem


def _work_dir(image_id: str) -> Path:
    """返回工作目录路径。"""
    return _TMP_DIR / "work" / image_id


def _sanitize_filename(name: str, max_len: int = 80) -> str:
    """将中文/英文混合字符串转为安全文件名。"""
    import re as _re
    # 保留中文、字母、数字、下划线、短横线
    name = _re.sub(r'[^\w\u4e00-\u9fff\-]', '_', name)
    # 合并连续下划线
    name = _re.sub(r'_+', '_', name).strip('_')
    return name[:max_len] if name else "slides"


def _content_name_from_frames(frames_tex: str) -> str:
    """从 frames.tex 中提取 frame 标题，拼合为内容文件名。

    例如 \\begin{frame}{体渲染公式} + \\begin{frame}{NeRF 训练}
    → "体渲染公式_NeRF_训练"
    """
    import re as _re
    titles = _re.findall(r'\\begin\{frame\}(?:\[[^\]]*\])?\{([^}]+)\}', frames_tex)
    if not titles:
        return "slides"
    # 取前 3 个标题，用下划线连接
    combined = "_".join(titles[:3])
    return _sanitize_filename(combined)


# ── 阶段 1：Prepare ──────────────────────────────────────────

def do_prepare(image_path: Path) -> dict:
    """创建工作目录，保存元数据。

    返回 metadata dict，供 Agent 读取。
    """
    image_path = image_path.resolve()
    if not image_path.exists():
        print(f"[error] 图片不存在: {image_path}", file=sys.stderr)
        sys.exit(1)

    img_id = _image_id(image_path)
    wdir = _work_dir(img_id)
    wdir.mkdir(parents=True, exist_ok=True)

    # 复制图片到工作目录
    dst_image = wdir / image_path.name
    if not dst_image.exists():
        shutil.copy2(image_path, dst_image)

    # 写入元数据
    metadata = {
        "image_id": img_id,
        "image_path": str(image_path),
        "image_copy": str(dst_image),
        "work_dir": str(wdir),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "prepared",
        "frames_tex": str(wdir / "frames.tex"),
        "prompt_template": str(_TEMPLATES_DIR / "prompt.md"),
    }
    meta_path = wdir / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[prepare] 工作目录已就绪: {wdir}")
    print(f"[prepare] 图片已复制到: {dst_image}")
    print(f"[prepare] 元数据: {meta_path}")
    print(f"[prepare] 等待 Agent 生成 frames.tex → {wdir / 'frames.tex'}")

    return metadata


# ── 阶段 3：Compile ──────────────────────────────────────────

def do_compile(image_path: Path, output_dir: Path) -> CompileResult:
    """读取 frames.tex，拼接 preamble，编译为 PDF。"""
    img_id = _image_id(image_path)
    wdir = _work_dir(img_id)

    frames_path = wdir / "frames.tex"
    if not frames_path.exists():
        print(f"[error] frames.tex 不存在: {frames_path}", file=sys.stderr)
        print("[error] 请先运行 --prepare，然后由 Agent 生成 frames.tex", file=sys.stderr)
        sys.exit(1)

    # 读取 preamble 和 frames
    preamble_path = _TEMPLATES_DIR / "preamble.tex"
    if not preamble_path.exists():
        print(f"[error] preamble.tex 不存在: {preamble_path}", file=sys.stderr)
        sys.exit(1)

    preamble = preamble_path.read_text(encoding="utf-8")
    frames = frames_path.read_text(encoding="utf-8")

    # 拼接为完整 .tex
    full_tex = preamble + "\n" + frames
    slides_tex_path = wdir / "slides.tex"
    slides_tex_path.write_text(full_tex, encoding="utf-8")
    print(f"[compile] 完整 .tex 已写入: {slides_tex_path}")

    # 编译
    result = compile_tex(slides_tex_path, output_dir=wdir)

    if result.success:
        # 从 frame 标题提取内容名
        content_name = _content_name_from_frames(frames)

        # 复制产物到 outputs —— 用内容名命名
        output_dir.mkdir(parents=True, exist_ok=True)
        final_pdf = output_dir / f"{content_name}.pdf"
        shutil.copy2(result.pdf_path, final_pdf)
        result.pdf_path = final_pdf
        print(f"[compile] ✅ 编译成功: {final_pdf}")

        # 复制原始手稿到同目录，使用同样的内容名
        image_path_resolved = image_path.resolve()
        if image_path_resolved.exists():
            manuscript_ext = image_path_resolved.suffix  # .jpg / .png 等
            manuscript_dst = output_dir / f"{content_name}_手稿{manuscript_ext}"
            shutil.copy2(image_path_resolved, manuscript_dst)
            print(f"[compile] 📋 原始手稿已复制: {manuscript_dst}")

        # 清理旧的 img_id 命名产物（如果存在）
        old_pdf = output_dir / f"{img_id}_slides.pdf"
        if old_pdf.exists() and old_pdf != final_pdf:
            old_pdf.unlink()

        # 生成预览 PNG 供 Agent 视觉检查
        pngs = pdf_to_png(final_pdf, output_dir=wdir)
        result.preview_pngs = pngs
        if pngs:
            print(f"[compile] 📸 预览图已生成（{len(pngs)} 页）：")
            for p in pngs:
                print(f"  {p}")

        # 更新 metadata
        meta_path = wdir / "metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["status"] = "compiled"
            meta["content_name"] = content_name
            meta["output_pdf"] = str(final_pdf)
            meta["compiled_at"] = datetime.now(timezone.utc).isoformat()
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        print(f"[compile] ❌ 编译失败", file=sys.stderr)
        print(result.log_summary, file=sys.stderr)

        # 更新 metadata
        meta_path = wdir / "metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["status"] = "compile_failed"
            meta["compile_errors"] = result.errors
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    return result


# ── CLI ──────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="src.generate",
        description="从手稿图片生成 Beamer 幻灯片 PDF。",
    )
    p.add_argument("image", help="手稿图片路径（jpg/png 等）")
    p.add_argument(
        "--output-dir", default=str(_OUTPUT_DEFAULT),
        help=f"产物目录，默认 {_OUTPUT_DEFAULT}",
    )
    p.add_argument("--prepare", action="store_true",
                   help="【三段式 Stage 1】仅创建工作目录并导出元数据")
    p.add_argument("--compile", action="store_true",
                   help="【三段式 Stage 3】读取 frames.tex 并编译为 PDF")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.prepare and args.compile:
        print("[error] --prepare 与 --compile 不能同时使用", file=sys.stderr)
        return 1

    image_path = Path(args.image).resolve()
    output_dir = Path(args.output_dir)

    if args.prepare:
        do_prepare(image_path)
        return 0

    if args.compile:
        result = do_compile(image_path, output_dir)
        return 0 if result.success else 1

    # 无参数时打印帮助
    print("[info] 请指定 --prepare 或 --compile。完整工作流：")
    print("  1. python -m src.generate <image> --prepare")
    print("  2. (Agent 生成 frames.tex)")
    print("  3. python -m src.generate <image> --compile")
    return 0


if __name__ == "__main__":
    sys.exit(main())
