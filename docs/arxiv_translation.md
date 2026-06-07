# arXiv 英文 PDF 到中文 PDF 翻译工作区

本目录用于把论文翻译流程固定为一个可重复的本地工作流：

```text
输入：一篇 arXiv 英文 PDF
输出：一篇中文排版 PDF
```

当前原则：

- 优先使用 arXiv LaTeX 源码，而不是直接从 PDF 抽文字再重排。
- 图片、公式、引用、表格结构尽量沿用原论文源码。
- 保留 Codex 会话内人工监督翻译流水线。
- 新增 DeepSeek API 自动翻译流水线：本地 Python 程序切分 LaTeX 片段并调用 DeepSeek，不依赖 Codex 持续在线。
- LaTeX/Python 只负责项目初始化、源码整理、PDF 编译和质量检查。

## 目录结构

```text
workflows/arxiv_translation/
  scripts/               # arXiv 翻译流程脚本
  templates/             # 术语规则和模型提示词
workspace/arxiv_translation/
  inbox/                 # 输入英文 PDF 的归档副本
  work/<arxiv_id>/       # 单篇论文的完整翻译工程
    input.pdf            # 输入 PDF
    metadata.json        # 论文 ID、路径、状态
    e-print.tar.gz       # arXiv 源码包，如果能下载到
    source/              # 解包后的英文 LaTeX 源码和图片
    zh/                  # 中文 LaTeX 源码，Codex 或 DeepSeek 脚本在这里翻译
    build_en/            # 英文源码试编译产物
    build_zh/            # 中文 PDF 编译产物
    api_backups/         # DeepSeek 脚本改写 TeX 前的备份
    notes/               # 翻译规则、术语表、人工检查记录
  outbox/                # 集中归档的中文 PDF、中文 TeX 和抽查截图
  diagnostics/           # LaTeX 环境测试产物
```

## 一篇论文的标准准备流程

先激活项目 Python 环境：

```bash
conda activate arxiv_translate
```

初始化翻译项目：

```bash
python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py prepare \
  "papers/auto_drive_3dgs/04_scene_generation_editing_data/未查到正式发表信息/2605.25373_Physics-Aware_3D_Gaussian_Editing_for_Driving_Scene_Generation.pdf"
```

脚本会：

- 从文件名识别 arXiv ID；
- 复制输入 PDF 到 `workspace/arxiv_translation/inbox/` 和 `workspace/arxiv_translation/work/<arxiv_id>/input.pdf`；
- 下载并解包 `https://arxiv.org/e-print/<arxiv_id>`；
- 自动识别主 `.tex` 文件；
- 初始化 `workspace/arxiv_translation/work/<arxiv_id>/zh/main_zh.tex`；
- 写入翻译规则和元数据。

如果同一个 arXiv ID 的工作目录已经存在，`prepare` 会默认拒绝覆盖，避免误删已翻译内容。确实需要重建时再显式添加 `--force`。

准备完成后，可以选择下面两条翻译流水线之一。

## 流水线 A：Codex 会话内翻译

```text
请按 workspace/arxiv_translation/work/<arxiv_id>/notes/translation_rules.md 翻译
workspace/arxiv_translation/work/<arxiv_id>/zh 中的 LaTeX 源码。

要求：
1. 保留公式、引用、label/ref/cite/url、图片路径、表格结构和 BibTeX key；
2. 标题、摘要、正文、图表标题翻译成中文学术论文风格；
3. 方法名、模型名、数据集名、指标名保留英文或采用约定术语；
4. 参考文献默认保留英文；
5. 翻译完成后运行：
   conda run -n arxiv_translate python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py build <arxiv_id>
6. 若编译失败，请根据日志修复，直到中文 PDF 成功生成并复制到源 PDF 同目录。
```

翻译完成后编译中文 PDF：

```bash
python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py build <arxiv_id>
```

最终产物写入集中归档：

```text
workspace/arxiv_translation/outbox/<arxiv_id>_zh.pdf
workspace/arxiv_translation/outbox/<arxiv_id>_zh.tex
```

同时，中文 PDF 会复制回源英文 PDF 所在目录，文件名为：

```text
<source_pdf_stem>_zh.pdf
```

例如：

```text
papers/auto_drive_3dgs/01_scene_reconstruction_dynamic_modeling/2311.18561_..._Rendering_zh.pdf
```

## 流水线 B：DeepSeek API 自动翻译

这条流水线适合批量跑，不需要 Codex 一直监控。它仍然使用本项目的 `prepare/build` 工程链，只把正文翻译改为本地脚本调用 DeepSeek Chat Completions API。

先设置密钥。不要把密钥写进项目文件：

```bash
export DEEPSEEK_API_KEY="sk-..."
```

默认参数：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TEMPERATURE=0.2
```

可用环境变量临时覆盖：

```bash
export DEEPSEEK_MODEL=deepseek-v4-pro
```

先做 dry-run，确认脚本能识别待翻译片段，但不会调用 API：

```bash
conda run -n arxiv_translate python workflows/arxiv_translation/scripts/deepseek_translate_tex.py \
  translate <arxiv_id> --dry-run --limit-chunks 5
```

正式翻译并编译：

```bash
conda run -n arxiv_translate python workflows/arxiv_translation/scripts/deepseek_translate_tex.py \
  translate <arxiv_id> --build
```

只翻译主文件：

```bash
conda run -n arxiv_translate python workflows/arxiv_translation/scripts/deepseek_translate_tex.py \
  translate <arxiv_id> --main-only --build
```

只翻译指定子文件：

```bash
conda run -n arxiv_translate python workflows/arxiv_translation/scripts/deepseek_translate_tex.py \
  translate <arxiv_id> --files sec/1_intro.tex sec/2_related_work.tex --build
```

脚本行为：

- 读取 `workspace/arxiv_translation/work/<arxiv_id>/zh/**/*.tex`；
- 跳过 `.bib/.bbl/.sty/.cls` 和公式、表格、算法等高风险环境；
- 翻译章节标题、图表标题、摘要和正文段落；
- 已经主要是中文的片段默认跳过，需要重译时加 `--force`；
- 改写前把原 TeX 备份到 `workspace/arxiv_translation/work/<arxiv_id>/api_backups/<timestamp>/`；
- API 调用日志写入 `workspace/arxiv_translation/work/<arxiv_id>/notes/deepseek_translation_log.jsonl`；
- 加 `--build` 后复用 `translate_arxiv_pdf.py build`，中文 PDF 仍会放入 `workspace/arxiv_translation/outbox/` 并复制回源 PDF 同目录。
- 编译时如遇缺失宏包文件，会输出对应的 `tlmgr install <pkg>` 安装建议（例如 `tlmgr install bbm`、`tlmgr install ifsym`）。本项目按官方 installer scheme-full 部署，默认不会触发；若使用 scheme-medium/small 等自定义子集才会用到，详见 [LaTeX 环境配置](latex_guide.md#本项目-latex-环境配置)。
- 遇到可恢复缺口（如 `ifsym.sty`、`bbm.sty`、`fontenc/inputenc` 兼容问题）会先做降级补丁并重试；仍失败时输出失败日志中的缺失文件与安装建议。

自动降级策略（不显著影响成品）：

- `\usepackage{ifsym}`：若本机没有 `ifsym.sty`，自动插入最小兼容符号定义（如 `\Letter`）以避免单命令中断。
- `\usepackage{bbm}`：若缺失会退化为 `\mathbb` 的兼容定义。
- `\usepackage{inputenc}` / `\usepackage{fontenc}`：当 XeLaTeX 编译触发兼容性报错时，自动改为注释该类行，改由 `fontspec/xeCJK` 接管编码与字体。
- `Undefined control sequence`：若日志内出现未定义命令，且命中白名单（当前包含 `\acronym`），则自动在 `main_zh.tex` 中注入 `\providecommand` 兼容定义后重试，保证不中断单篇编译。
- `\macro中文` 相邻命令边界：若译文里出现 `\acronym中文` 或 `\acronym\中文`，自动改写为 `\acronym{}`，避免 XeTeX 在中文上下文下误解析控制序列导致编译中断。该修复与降级宏定义配套，优先执行且不影响公式/引用。
- 若仍有未定义命令/宏包，构建失败时会附带提示并建议补齐对应环境。
- 构建会先尝试一次标准编译，若日志里命中可恢复问题（如缺少 `ifsym`/`bbm` 或已知 XeLaTeX 兼容性问题）会自动打补丁并重试一次编译。

示例（缺包降级编译）：

```bash
python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py build 2502.13144
```

如果遇到 `\acronym` 等译文宏未定义，也会自动打补丁示例：

```bash
python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py build 2503.18108
```

当日志包含 `Undefined control sequence` 时，脚本会输出：

```text
[build] 已注入未定义命令兼容定义：\\acronym
[build] 已修复中文相邻命令边界：\\acronym
```

然后继续执行第二轮编译。

DeepSeek 的系统提示词保存在：

```text
workflows/arxiv_translation/templates/deepseek_system_prompt.md
```

通用术语规则保存在：

```text
workflows/arxiv_translation/templates/translation_rules.md
```

单篇论文的专用规则保存在：

```text
workspace/arxiv_translation/work/<arxiv_id>/notes/translation_rules.md
```

如果某篇论文有特殊术语，优先改单篇规则文件；DeepSeek 脚本会把它追加到系统提示词后面。

## 从 PDF 到中文 PDF 的一条命令链

三步式：

```bash
conda activate arxiv_translate

python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py prepare /path/to/paper.pdf

export DEEPSEEK_API_KEY="sk-..."

python workflows/arxiv_translation/scripts/deepseek_translate_tex.py translate <arxiv_id> --build
```

一条命令式：

```bash
conda activate arxiv_translate

export DEEPSEEK_API_KEY="sk-..."

python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py api-translate /path/to/paper.pdf
```

如果工作目录已存在并且要沿用它：

```bash
python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py api-translate /path/to/paper.pdf --reuse-work
```

如果只想检查会翻译哪些片段，不调用 DeepSeek：

```bash
python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py api-translate /path/to/paper.pdf --reuse-work --dry-run --limit-chunks 5
```

## 从 arXiv ID 到中英双 PDF

如果只有文章 ID，没有本地 PDF，可以直接使用 `translate-id` 接口：

```bash
conda activate arxiv_translate
export DEEPSEEK_API_KEY="sk-..."

python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py translate-id 2405.17705
```

脚本会：

- 接受 `2405.17705`、`2405.17705v2` 或 arXiv URL；
- 先在 `papers/` 中查找已有英文 PDF；
- 找不到时从 `https://arxiv.org/pdf/<arxiv_id>.pdf` 下载英文 PDF；
- 复制英文 PDF 到 `workspace/arxiv_translation/outbox/<arxiv_id>_en.pdf`；
- 复用 `prepare` 和 DeepSeek API 翻译流程生成中文 PDF；
- 输出 `workspace/arxiv_translation/outbox/<arxiv_id>_zh.pdf`。

如果中文 PDF 已存在，默认直接复用并输出路径；需要重建工程或重译时，分别添加 `--force-prepare` 或 `--force-translate`。

机器可读输出：

```bash
python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py translate-id 2405.17705 --json
```

指定输出目录：

```bash
python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py translate-id 2405.17705 --output-dir /path/to/result
```

## 环境检查

```bash
python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py doctor
```

必须可用：

- Python：conda 环境 `arxiv_translate`（只装本能力的 Python 依赖，不要装 LaTeX 工具）
- LaTeX：官方 TeX Live 2026 装于 `/data/texlive/2026`（scheme-full），通过 `~/.bashrc` 加入 `PATH` 暴露给所有 conda 环境
  - `xelatex`、`latexmk`、`tlmgr` 均应解析到 `/data/texlive/2026/bin/x86_64-linux/`
  - `ctex.sty`、`xeCJK.sty` 由 scheme-full 自带，无需单独装
- 辅助：`pdftotext`（系统包 `poppler-utils`，源码不可用时用于降级抽取）
- 中文字体：scheme-full 自带 fandol；系统级 Noto CJK 可补充

完整安装步骤与 apt/conda/installer 选型对比见 [LaTeX 环境配置](latex_guide.md#本项目-latex-环境配置)。

## 翻译规则

基础规则保存在 [workflows/arxiv_translation/templates/translation_rules.md](../workflows/arxiv_translation/templates/translation_rules.md)。

每篇论文初始化时会复制一份到：

```text
workspace/arxiv_translation/work/<arxiv_id>/notes/translation_rules.md
```

如果某篇论文需要专门术语，优先追加到该论文自己的 `notes/translation_rules.md`，不要改动全局模板。

## 说明

Codex 流水线适合需要人工控制质量、逐段修复 LaTeX 的论文。DeepSeek API 流水线适合先批量得到可编译中文初稿，再由 Codex 或人工抽查润色。两条流水线共用同一套 `prepare/build` 和同一份工作目录。
