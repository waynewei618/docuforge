"""LaTeX 编译相关的兼容/降级/失败分析逻辑。

从旧 translate_arxiv_pdf.py 中拆出，让 pipeline.py 聚焦流水线编排。
"""
from __future__ import annotations

import re
from pathlib import Path


# ---------- 模板与常量 ----------

IFSYM_FALLBACK = r"""\IfFileExists{ifsym.sty}{\usepackage[misc]{ifsym}}{%
% Auto fallback for missing ifsym.sty: keep compileable in environments without ifsym.
  \providecommand{\Letter}{\ensuremath{\star}}
  \providecommand{\Square}{\ensuremath{\square}}
  \providecommand{\Circle}{\ensuremath{\bullet}}
  \providecommand{\CIRCLE}{\ensuremath{\bullet}}
  \providecommand{\Diamondsuit}{\diamond}
  \providecommand{\X}{\times}
}"""

XELATEX_ENCODING_FALLBACK = (
    "% {line}\n"
    "% Auto XeLaTeX compatibility: legacy utf8/font encoding packages are unnecessary."
)

BBDING_FALLBACK = (
    "% Auto fallback: bbding.sty not found, use plain symbol fallback.\n"
    "% bbding 常见符号在不完整环境中的兼容定义。\n"
    "\\providecommand{\\Checkmark}{\\checkmark}\n"
    "\\providecommand{\\CheckmarkBold}{\\checkmark}\n"
    "\\providecommand{\\cmark}{\\checkmark}\n"
    "\\providecommand{\\xmark}{\\ensuremath{\\times}}\n"
    "\\providecommand{\\XSolidBrush}{\\ensuremath{\\times}}\n"
)

MISSING_PKG_HINTS = {
    # 项目默认 TeX Live (官方 installer scheme-full) 已包含所有 CTAN 宏包，
    # 这里命中通常说明环境是 scheme-medium/small。用 tlmgr 单包补齐即可。
    "bbm.sty":    "tlmgr install bbm",
    "ifsym.sty":  "tlmgr install ifsym",
    "bbding.sty": "tlmgr install bbding",
    "xcolor.sty": "tlmgr install xcolor",
    "ctex.sty":   "tlmgr install ctex",
    "xeCJK.sty":  "tlmgr install xecjk",
}

UNDEFINED_COMMAND_FALLBACKS = {
    # 注：pdfTeX 系列（\pdfminorversion 等）由 PDFTEX_COMPAT_BLOCK 在 preamble 早期统一注入，
    # 不放在这里以避免重复定义。
    "ignorespaces": "\\providecommand{\\ignorespaces}{}\n",
    "acronym": "\\providecommand{\\acronym}{}\n",
    "Checkmark":    "\\providecommand{\\Checkmark}{\\checkmark}\n",
    "CheckmarkBold": "\\providecommand{\\CheckmarkBold}{\\checkmark}\n",
    "XSolidBrush":  "\\providecommand{\\XSolidBrush}{\\ensuremath{\\times}}\n",
    "xmark":        "\\providecommand{\\xmark}{\\ensuremath{\\times}}\n",
    "cmark":        "\\providecommand{\\cmark}{\\checkmark}\n",
}

FALLBACK_TEMPLATE = "\n".join([
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
])


# pdfTeX 原始寄存器在 XeLaTeX 下未定义。某些会议模板（如 ieeeconf）
# 会在 preamble 早期写 `\pdfminorversion=4`，必须 *先于* 这些语句给出兜底定义，
# 否则按需 fallback 来不及。这一块由 prepare 阶段预防性注入到紧随 \documentclass 之后。
PDFTEX_COMPAT_BLOCK = (
    "% Auto: pdfTeX-compat shims for XeLaTeX (must precede any \\pdf* register usage).\n"
    "\\ifx\\pdfminorversion\\undefined\\newcount\\pdfminorversion\\fi\n"
    "\\ifx\\pdfobjcompresslevel\\undefined\\newcount\\pdfobjcompresslevel\\fi\n"
    "\\ifx\\pdfcompresslevel\\undefined\\newcount\\pdfcompresslevel\\fi\n"
    "\\ifx\\pdfoptionpdfminorversion\\undefined\\newcount\\pdfoptionpdfminorversion\\fi\n"
    "\\ifx\\pdfglyphtounicode\\undefined\\def\\pdfglyphtounicode#1#2{}\\fi\n"
    "\\ifx\\pdfgentounicode\\undefined\\newcount\\pdfgentounicode\\fi\n"
)


# ---------- TeX 文本规范化 ----------

def normalize_optional_packages(tex: str) -> str:
    tex = re.sub(
        r"(?m)^(?!\s*%)\\usepackage(?:\[[^]]*\])?\{ifsym\}\s*$",
        lambda _m: IFSYM_FALLBACK, tex,
    )
    tex = re.sub(
        r"(?m)^(?!\s*%)\\usepackage(?:\[[^]]*\])?\{bbding\}\s*$",
        lambda _m: BBDING_FALLBACK, tex,
    )
    tex = re.sub(
        r"(?m)^(?!\s*%)\\usepackage\{bbm\}\s*$",
        lambda _m: r"% \usepackage{bbm}\n\providecommand{\mathbbm}[1]{\mathbb{#1}}",
        tex,
    )
    return tex


def normalize_graphics_px_units(tex: str) -> str:
    """图像裁切 `trim={10px ...}` → pt，避免 'Illegal unit of measure'。"""
    return re.sub(r"([0-9]+)px", r"\1pt", tex)


def normalize_xelatex_encoding(tex: str) -> str:
    tex = re.sub(
        r"(?m)^(?!\s*%)\\usepackage\[[^]]*\]\{inputenc\}\s*(%.*)?$",
        lambda m: XELATEX_ENCODING_FALLBACK.format(
            line=m.group(0).strip() + " (XeLaTeX 下已注释)"
        ), tex,
    )
    tex = re.sub(
        r"(?m)^(?!\s*%)\\usepackage(?:\[[^]]*\])?\{fontenc\}\s*(%.*)?$",
        lambda m: XELATEX_ENCODING_FALLBACK.format(
            line=m.group(0).strip() + " (XeLaTeX 下已注释)"
        ), tex,
    )
    return tex


def inject_chinese_preamble(tex: str) -> str:
    if r"\usepackage" in tex and "ctex" in tex:
        return tex
    is_acmart = re.search(r"\\documentclass(?:\[[^\]]*\])?\{acmart\}", tex) is not None
    cjk_lines = []
    if not is_acmart:
        cjk_lines.append(r"\usepackage[UTF8,fontset=none]{ctex}")
    cjk_lines.extend([
        r"\usepackage{fontspec}",
        r"\usepackage{xeCJK}",
        r"\setCJKmainfont{Noto Serif CJK SC}",
        r"\setCJKsansfont{Noto Sans CJK SC}",
        r"\setCJKmonofont{Noto Sans Mono CJK SC}",
        r"\setlength{\columnsep}{0.30in}",
        r"\setlength{\columnseprule}{0.35pt}",
    ])
    cjk = "\n".join(cjk_lines)
    # 注入顺序：\documentclass → PDFTEX_COMPAT_BLOCK（兜底 \pdfminorversion 等）→ 中文 preamble
    inject = "\n" + PDFTEX_COMPAT_BLOCK + cjk
    pattern = re.compile(r"^(?!\s*%)(.*\\documentclass(?:\[[^\]]*\])?\{[^}]+\}.*)$", re.MULTILINE)
    return pattern.sub(
        lambda match: match.group(1) + inject,
        normalize_xelatex_encoding(normalize_optional_packages(tex)),
        count=1,
    )


def normalize_optional_packages_in_dir(tex_root: Path) -> int:
    updated = 0
    for path in sorted(tex_root.rglob("*.tex")):
        text = path.read_text(encoding="utf-8", errors="replace")
        normalized = normalize_graphics_px_units(
            normalize_xelatex_encoding(normalize_optional_packages(text))
        )
        if normalized != text:
            path.write_text(normalized, encoding="utf-8")
            updated += 1
    return updated


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
        return block_re.sub(lambda _m: replacement, tex, count=1)

    return re.sub(
        r"\\bibliographystyle\{[^}]+\}\s*\\bibliography\{[^}]+\}",
        lambda _m: replacement, tex, count=1, flags=re.DOTALL,
    )


# ---------- 编译失败分析与自动 fallback ----------

def _has_command_definition(tex: str, command: str) -> bool:
    command = command.lstrip("\\")
    escaped = re.escape(command)
    patterns = [
        rf"\\(?:newcommand|renewcommand|providecommand)\*?\s*\{{\\{escaped}\}}",
        rf"\\DeclareRobustCommand\*?\s*\{{\\{escaped}\}}",
        rf"\\newcount\\{escaped}\b",
        rf"\\def\\{escaped}\b",
        rf"\\edef\\{escaped}\b",
        rf"\\xdef\\{escaped}\b",
        rf"\\let\\{escaped}\s*=?",
    ]
    return any(re.search(pattern, tex, flags=re.MULTILINE) is not None for pattern in patterns)


def _inject_missing_command_fallbacks(main_tex: Path, missing_commands: list[str]) -> bool:
    if not missing_commands or not main_tex.exists():
        return False
    text = main_tex.read_text(encoding="utf-8", errors="replace")
    documentclass_match = re.search(r"(?m)^\\documentclass(?:\[[^]]*\])?\{[^}]+\}\s*$", text)
    begin_document_match = re.search(r"(?m)^\\begin\{document\}\s*$", text)
    if documentclass_match is None and begin_document_match is None:
        return False

    insertion_idx = documentclass_match.end() if documentclass_match else begin_document_match.start()
    preamble = text[:insertion_idx]
    insertion_token = text[insertion_idx:]
    block_lines: list[str] = []
    for command in missing_commands:
        cmd = command.lstrip("\\")
        if cmd in UNDEFINED_COMMAND_FALLBACKS and cmd not in {"", "begin", "end"}:
            if not _has_command_definition(text, cmd):
                block_lines.append(UNDEFINED_COMMAND_FALLBACKS[cmd])

    if not block_lines:
        return False

    fallback_block = (
        "\n\n% Auto fallback: keep compileable for translated control sequences.\n"
        + "\n".join(block_lines) + "\n"
    )
    main_tex.write_text(preamble + fallback_block + insertion_token, encoding="utf-8")
    return True


def _normalize_cjk_adjacent_macros(tex_root: Path, commands: list[str]) -> bool:
    if not commands:
        return False
    changed = False
    for path in sorted(tex_root.glob("**/*.tex")):
        text = path.read_text(encoding="utf-8", errors="replace")
        fixed = text
        for command in commands:
            cmd = command.lstrip("\\")
            if not cmd or cmd in {"begin", "end"}:
                continue
            pattern = re.compile(rf"\\{re.escape(cmd)}(?=[\u4e00-\u9fff])")
            fixed = pattern.sub(rf"\\{cmd}{{}}", fixed)
            pattern = re.compile(rf"\\{re.escape(cmd)}\\(?=[\u4e00-\u9fff])")
            fixed = pattern.sub(rf"\\{cmd}{{}}", fixed)
        if fixed != text:
            path.write_text(fixed, encoding="utf-8")
            changed = True
    return changed


def _find_prebuilt_bbl(main_tex: Path, bib_names: list[str]) -> Path | None:
    """在 main_tex 同目录及其 source 兄弟目录里，找一个预生成的非空 .bbl。

    优先匹配 \\bibliography{xxx} 中列出的名字，找不到再回退到目录里任意 .bbl。
    """
    zh_dir = main_tex.parent
    work_dir = zh_dir.parent
    source_dir = work_dir / "source"

    candidates: list[Path] = []
    for stem in bib_names:
        for d in (zh_dir, source_dir):
            p = d / f"{stem}.bbl"
            if p.exists():
                candidates.append(p)
    for d in (zh_dir, source_dir):
        if d.exists():
            candidates.extend(sorted(d.glob("*.bbl")))

    seen: set[Path] = set()
    for bbl in candidates:
        if bbl in seen:
            continue
        seen.add(bbl)
        try:
            if bbl.stat().st_size > 0 and "\\bibitem" in bbl.read_text(
                encoding="utf-8", errors="replace"
            ):
                return bbl
        except OSError:
            continue
    return None


def _disable_bibliography_in_tex(main_tex: Path) -> bool:
    """处理 bibtex 失败：优先用预生成 .bbl 兜底，找不到才注释掉整段。"""
    text = main_tex.read_text(encoding="utf-8", errors="replace")
    pattern = re.compile(
        r"\\bibliographystyle\{[^}]+\}\s*\\bibliography\{([^}]+)\}",
        flags=re.MULTILINE,
    )
    match = pattern.search(text)
    if match is None:
        return _comment_out_bibliography(main_tex, text)

    bib_names = [s.strip() for s in match.group(1).split(",") if s.strip()]
    bbl = _find_prebuilt_bbl(main_tex, bib_names)
    if bbl is None:
        return _comment_out_bibliography(main_tex, text)

    # 把 .bbl 复制到 main_tex 同目录（如果不在那里），改写引用为 \input{...bbl}
    target_bbl = main_tex.parent / bbl.name
    if bbl.resolve() != target_bbl.resolve():
        target_bbl.write_bytes(bbl.read_bytes())

    replacement = (
        "% Auto fallback: bibtex failed; inlined pre-built bbl to preserve citations.\n"
        f"\\input{{{target_bbl.stem}.bbl}}"
    )
    new_text = pattern.sub(replacement, text, count=1)
    if new_text == text:
        return _comment_out_bibliography(main_tex, text)
    main_tex.write_text(new_text, encoding="utf-8")
    return True


def _comment_out_bibliography(main_tex: Path, text: str) -> bool:
    """最后的兜底：把 \\bibliographystyle/\\bibliography 整段注释掉。"""
    changed = False
    pattern = re.compile(
        r"\n\\bibliographystyle\{[^}]+\}\s*\\bibliography\{[^}]+\}\n",
        flags=re.MULTILINE,
    )

    def repl(_match: re.Match[str]) -> str:
        nonlocal changed
        changed = True
        return (
            "\n% Auto fallback: disabled bibtex block due parse error.\n"
            + "\n".join(f"% {line}" for line in _match.group(0).strip().splitlines())
            + "\n"
        )

    new_text = pattern.sub(repl, text)
    if not changed:
        pattern2 = re.compile(
            r"\n\\bibliographystyle\{[^}]+\}\s*\n\\bibliography\{[^}]+\}\n",
            flags=re.MULTILINE,
        )
        new_text = pattern2.sub(repl, new_text)
        changed = new_text != text

    if not changed:
        macro_pattern = re.compile(
            r"^\s*\\bib(?:style|data)\{[^}]+\}\s*$", flags=re.MULTILINE
        )
        changed_lines: list[str] = []
        for line in new_text.splitlines():
            if macro_pattern.match(line):
                changed_lines.append("% " + line)
                changed = True
            else:
                changed_lines.append(line)
        new_text = "\n".join(changed_lines)
        if changed and new_text and not new_text.endswith("\n"):
            new_text += "\n"

    if changed:
        main_tex.write_text(new_text, encoding="utf-8")
    return changed


def _parse_latex_failures(log_path: Path) -> tuple[list[str], list[str], bool, list[str], bool]:
    if not log_path.exists():
        return [], [], False, [], False

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    missing_files = []
    missing_commands = []
    has_glyph_error = False
    glyph_fonts: list[str] = []

    for idx, line in enumerate(lines):
        missing_match = re.search(
            r"^!?\s*(?:LaTeX Error: File `([^']+)'\s*not found\.|I can't find file `([^']+)'\.)$",
            line,
        )
        if missing_match:
            missing_files.append(next(name for name in missing_match.groups() if name))

        if "Undefined control sequence." in line:
            for j in range(idx, min(idx + 6, len(lines))):
                missing_commands.extend(
                    "\\" + m.group(1)
                    for m in re.finditer(r"\\([A-Za-z@]+)(?=[^A-Za-z@]|$)", lines[j])
                )

        glyph_match = re.search(r"Cannot use XeTeXglyph with (.+); not a native platform font\.", line)
        if glyph_match:
            has_glyph_error = True
            glyph_fonts.append(glyph_match.group(1).strip())

    has_bibtex_error = any(
        "I was expecting a `" in line
        or "Error--" in line and "a `,'" in line
        or "I don't understand this entry" in line
        for line in lines
    )
    has_bibtex_error = has_bibtex_error or any(
        "Fatal error (all \"end of file\" reached)" in line for line in lines
    )
    has_bibtex_error = has_bibtex_error or any(
        "No file" in line and ".bbl" in line for line in lines
    )

    blg_path = log_path.with_suffix(".blg")
    if blg_path.exists():
        blg_lines = blg_path.read_text(encoding="utf-8", errors="replace").splitlines()
        has_bibtex_error = has_bibtex_error or any(
            "I was expecting a `" in line
            or "---line" in line
            or "Error--" in line and "a `,'" in line
            or "I don't understand this entry" in line
            for line in blg_lines
        )
        has_bibtex_error = has_bibtex_error or any("Fatal error" in line for line in blg_lines)

    return (
        sorted(set(missing_files)),
        sorted(set(missing_commands)),
        has_glyph_error,
        sorted(set(glyph_fonts)),
        has_bibtex_error,
    )


def summarize_latex_failures(log_path: Path) -> None:
    if not log_path.exists():
        print(f"[build] 编译日志未生成：{log_path}")
        return

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    missing_files, missing_commands, *_ = _parse_latex_failures(log_path)

    if missing_files:
        print("[build] 检测到缺失宏包文件:")
        for item in missing_files:
            msg = MISSING_PKG_HINTS.get(item, "")
            print(f"  - {item}" + (f"（建议: {msg}）" if msg else ""))

    if missing_commands:
        print("[build] 检测到未定义命令:")
        for item in missing_commands:
            print(f"  - {item}")

    if not missing_files and not missing_commands:
        tail = "\n".join(lines[-30:])
        print(f"[build] LaTeX 失败片段（最近 30 行）:\n{tail}")


def is_nonfatal_latex_failure(log_path: Path, pdf_path: Path) -> bool:
    """判断 LaTeX 失败日志是否为可接受的'非致命'警告型问题。"""
    if not log_path.exists() or not pdf_path.exists():
        return False
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if "No pages of output." in text:
        return False
    if re.search(r"^! (?:Package|Class|LaTeX Error|Undefined|Missing|Extra|Emergency stop|Fatal error)", text, re.M):
        return False
    if "Latexmk:.*Had errors" in text:
        return False
    return True


def apply_auto_fallbacks_from_log(log_path: Path, zh: Path, main_tex: Path) -> bool:
    missing_files, missing_commands, has_glyph_error, _, has_bibtex_error = _parse_latex_failures(log_path)
    changed = False

    if any(item in {"ifsym.sty", "bbm.sty", "bbding.sty"} for item in missing_files):
        if normalize_optional_packages_in_dir(zh):
            print("[build] 已应用缺失可选包兼容补丁", flush=True)
            changed = True

    if has_glyph_error:
        if normalize_optional_packages_in_dir(zh):
            print("[build] 检测到 XeTeXglyph 兼容报错，已添加 XeLaTeX 兼容注释", flush=True)
            changed = True

    if missing_commands and main_tex.exists():
        if _inject_missing_command_fallbacks(main_tex, missing_commands):
            print(f"[build] 已注入未定义命令兼容定义：{', '.join(missing_commands)}", flush=True)
            changed = True
        if _normalize_cjk_adjacent_macros(zh, missing_commands):
            print(f"[build] 已修复中文相邻命令边界：{', '.join(missing_commands)}", flush=True)
            changed = True

    if has_bibtex_error and main_tex.exists():
        if _disable_bibliography_in_tex(main_tex):
            print("[build] 已禁用 BibTeX 参考文献块并尝试继续编译", flush=True)
            changed = True

    if not changed:
        for item in missing_files:
            msg = MISSING_PKG_HINTS.get(item)
            if msg:
                print(f"[build] 缺失宏包可手动补齐（{item}）：{msg}")
    return changed
