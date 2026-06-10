"""LaTeX 编译工具：编译 Beamer .tex 为 PDF，支持错误日志解析。"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CompileResult:
    """编译结果。"""
    success: bool
    pdf_path: Path | None = None
    log_summary: str = ""
    errors: list[str] = field(default_factory=list)
    return_code: int = 0
    preview_pngs: list[Path] = field(default_factory=list)


def _parse_latex_errors(log_path: Path) -> list[str]:
    """从 .log 文件中提取关键错误行。"""
    if not log_path.exists():
        return ["[compile] .log 文件不存在"]

    errors: list[str] = []
    log_text = log_path.read_text(encoding="utf-8", errors="replace")

    # 匹配 ! 开头的 LaTeX 错误
    for m in re.finditer(r"^! (.+?)$", log_text, re.MULTILINE):
        errors.append(m.group(0))

    # 匹配 l.NNN 行号提示
    for m in re.finditer(r"^l\.\d+.*$", log_text, re.MULTILINE):
        errors.append(m.group(0))

    # 匹配 Fatal error
    for m in re.finditer(r"(?:Fatal|Emergency).+$", log_text, re.MULTILINE):
        errors.append(m.group(0))

    return errors[:30]  # 限制条数，避免太长


def compile_tex(
    tex_path: Path,
    *,
    output_dir: Path | None = None,
    max_runs: int = 2,
) -> CompileResult:
    """用 latexmk + xelatex 编译 .tex 文件。

    Args:
        tex_path: 要编译的 .tex 文件路径。
        output_dir: PDF 输出目录，默认与 .tex 同目录。
        max_runs: latexmk 最大编译轮数。

    Returns:
        CompileResult 包含成功标志、PDF 路径和错误信息。
    """
    tex_path = tex_path.resolve()
    if not tex_path.exists():
        return CompileResult(success=False, log_summary=f".tex 文件不存在: {tex_path}")

    work_dir = tex_path.parent
    if output_dir is None:
        output_dir = work_dir

    cmd = [
        "latexmk",
        "-xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={output_dir}",
        str(tex_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return CompileResult(
            success=False,
            log_summary="编译超时（120 秒）",
            return_code=-1,
        )
    except FileNotFoundError:
        return CompileResult(
            success=False,
            log_summary="latexmk 未找到，请确认 TeX Live 已安装并在 PATH 中",
            return_code=-1,
        )

    # 查找 PDF
    pdf_name = tex_path.stem + ".pdf"
    pdf_path = output_dir / pdf_name

    # 解析日志
    log_path = output_dir / (tex_path.stem + ".log")
    errors = _parse_latex_errors(log_path)

    if proc.returncode == 0 and pdf_path.exists():
        return CompileResult(
            success=True,
            pdf_path=pdf_path,
            return_code=0,
        )

    # 编译失败：汇总错误
    summary_parts = [f"latexmk 退出码: {proc.returncode}"]
    if errors:
        summary_parts.append("--- LaTeX 错误 ---")
        summary_parts.extend(errors)
    if proc.stderr and proc.stderr.strip():
        summary_parts.append("--- stderr ---")
        summary_parts.append(proc.stderr[:2000])

    return CompileResult(
        success=False,
        log_summary="\n".join(summary_parts),
        errors=errors,
        return_code=proc.returncode,
    )


def clean_aux(work_dir: Path) -> None:
    """清理 LaTeX 辅助文件。"""
    exts = {".aux", ".log", ".fls", ".fdb_latexmk", ".nav", ".out", ".snm", ".toc", ".vrb", ".xdv"}
    for f in work_dir.iterdir():
        if f.suffix in exts:
            f.unlink(missing_ok=True)


def pdf_to_png(pdf_path: Path, output_dir: Path | None = None, dpi: int = 200) -> list[Path]:
    """将 PDF 每页转为 PNG 图片，供 Agent 视觉检查。

    依赖系统命令 pdftoppm（poppler-utils）。

    Returns:
        PNG 文件路径列表，按页码排序。
    """
    pdf_path = pdf_path.resolve()
    if not pdf_path.exists():
        return []

    if output_dir is None:
        output_dir = pdf_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = output_dir / "slide"

    try:
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), str(pdf_path), str(prefix)],
            capture_output=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    # pdftoppm 输出 slide-1.png, slide-2.png, ...
    pngs = sorted(output_dir.glob("slide-*.png"))
    return pngs
