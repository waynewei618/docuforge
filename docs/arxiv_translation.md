# arXiv 英文 PDF 到中文 PDF 翻译工作流

```text
输入：arXiv ID（或本地 PDF）
输出：英文 PDF + 中文排版 PDF（双 PDF 落到 output/）
```

设计原则：

- 优先使用 arXiv LaTeX 源码，而不是从 PDF 抽文字再重排；
- 图片、公式、引用、表格结构尽量沿用原论文源码；
- 整个流水线一条命令跑完，无子命令；
- 翻译后端可显式切换（DeepSeek API / Claude Code subagent），不做运行时自动检测；
- 调试缓存保留在 `tmp/`，最终产物落到 `output/`，二者都不进 git。

## 目录结构

```text
workflows/arxiv_translation/
  src/                            # 流水线代码
    translate.py                  # CLI 入口（python -m src.translate）
    pipeline.py                   # 流水线编排
    tex_translator.py             # chunk 切分 + 调 backend
    backends.py                   # DeepSeek / Claude Code 后端
    latex_fallbacks.py            # LaTeX 兼容兜底
  templates/
    deepseek_system_prompt.md     # 翻译 system prompt
    translation_rules.md          # 通用术语规则模板
  tmp/                            # 运行时缓存（gitignored）
    inbox/                        # 输入 PDF 归档副本
    work/<arxiv_id>/              # 单篇论文完整工程：source/zh/notes/build_zh/api_backups
    outbox/                       # build 调试归档（每篇 zh.pdf/zh.tex 副本）
    diagnostics/  agent_logs/     # LaTeX 诊断 / 子 agent 日志
  output/                         # 最终产物（gitignored）：<id>_en.pdf / <id>_zh.pdf
```

`tmp/work/<arxiv_id>/` 的内部结构：

```text
input.pdf            # 输入英文 PDF
e-print.tar.gz       # arXiv 源码包（若能下到）
source/              # 解包后的英文 LaTeX 工程
zh/                  # 中文 LaTeX 工程（流水线在此原地翻译）
build_zh/            # latexmk 编译产物（中间文件 + 最终 main_zh.pdf）
api_backups/<stamp>/ # 每次翻译改写前的 TeX 备份
notes/               # 单篇翻译规则、日志
metadata.json        # 论文 ID、来源、状态等元数据
```

## 主接口

```bash
cd workflows/arxiv_translation
conda run -n docuforge python -m src.translate <input> [选项]
```

`<input>` 接受：

- 裸 arXiv ID：`2405.17705`
- 带版本号：`2405.17705v2`
- arXiv URL：`https://arxiv.org/abs/2405.17705`
- 本地 PDF 路径：`./papers/.../foo.pdf`（从文件名识别 ID）

### 选项

| 选项 | 默认 | 说明 |
|---|---|---|
| `--output-dir <dir>` | `./output/` | 产物目录 |
| `--backend {deepseek,claude,agy}` | `agy` | 翻译后端 |
| `--main <name>` | `main_zh.tex` | 中文主 TeX 文件名 |
| `--force` | — | 即使 `output/<id>_zh.pdf` 存在也强制重做 |
| `--limit-chunks <N>` | — | 每文件至多翻译 N 个 chunk（调试用） |
| `--main-only` | — | 只翻译 `--main` 一个文件 |
| `--no-source` | — | 不下载 arXiv e-print 源码（仅 PDF 抽取降级） |
| `--json` | — | 机器可读输出 |


## 翻译后端

### Antigravity subagent (agy)（默认）

适合在 Antigravity 内运行时复用当前会话。调用 `agy -p` headless 模式：

```bash
cd workflows/arxiv_translation
conda run -n docuforge python -m src.translate 2405.17705
```

或者显式指定 `--backend agy`：

```bash
conda run -n docuforge python -m src.translate 2405.17705 --backend agy
```

模型解析：优先读取 `AGY_SUBAGENT_MODEL` 环境变量，未设定则由 agy 客户端选用其默认模型。不需要单独配 API key，认证自动继承 Antigravity 的 session。

### DeepSeek

适合离线终端批量翻译。要求 `DEEPSEEK_API_KEY` 环境变量：

```bash
export DEEPSEEK_API_KEY="sk-..."
cd workflows/arxiv_translation
conda run -n docuforge python -m src.translate 2405.17705 --backend deepseek
```

通过 OpenAI 兼容的 `chat/completions` 接口调 DeepSeek，自动重试、按 chunk 串行。

### Claude Code subagent

适合在 Claude Code 内运行时复用当前 session 认证。调用 `claude -p` headless 模式：

```bash
cd workflows/arxiv_translation
conda run -n docuforge python -m src.translate 2405.17705 --backend claude
```

模型解析：优先读取 `CLAUDE_CODE_SUBAGENT_MODEL` 环境变量，未设定则由 claude 客户端选用其默认模型。不需要单独配 API key，认证自动继承 Claude Code 的 session。

> **何时选哪个**：在 Antigravity 内运行希望走其 subagent 链 → 默认 `agy` 即可；离线终端、批量、不需要复用对话上下文 → `deepseek`；在 Claude Code 内希望走其 subagent 链 → `claude`。三个后端共享同一份 chunk 切分与 `system_prompt`，翻译质量主要取决于模型本身。

## 端到端示例

```bash
cd workflows/arxiv_translation

# 1. 标准跑法（DeepSeek 后端）
export DEEPSEEK_API_KEY="sk-..."
conda run -n docuforge python -m src.translate 2405.17705
# → output/2405.17705_en.pdf, output/2405.17705_zh.pdf

# 2. 用本地 PDF（自动从文件名识别 ID）
conda run -n docuforge python -m src.translate \
  ../../papers/auto_drive_3dgs/01_scene_reconstruction_dynamic_modeling/2502.14235_OG-Gaussian_Occupancy_Based_Street_Gaussians_for_Autonomous_Driving.pdf

# 3. 输出到自定义目录
conda run -n docuforge python -m src.translate 2405.17705 --output-dir /tmp/x

# 4. Claude Code subagent 后端
conda run -n docuforge python -m src.translate 2405.17705 --backend claude

# 5. 强制重做
conda run -n docuforge python -m src.translate 2405.17705 --force

# 6. 仅翻译主 TeX 的前 5 个 chunk（调试用）
conda run -n docuforge python -m src.translate 2405.17705 --main-only --limit-chunks 5
```

## 幂等与缓存

- 默认看到 `output/<id>_zh.pdf` 已存在就跳过翻译/编译，加 `--force` 强制重跑。
- 重跑时 `tmp/work/<id>/` 会被清空并重建（force 路径）；不 force 时复用现有 work 缓存（继续翻译没译完的 chunk）。
- 每次翻译前会把当前 `zh/<file>.tex` 备份到 `tmp/work/<id>/api_backups/<timestamp>/`，可手动回滚。
- 编译中间产物 `tmp/work/<id>/build_zh/` 保留，方便 debug。

## 翻译流水线内部步骤

1. **resolve_input** — 解析 `<input>` 为 arxiv id（+ 可选源 PDF 路径）
2. **ensure_english_pdf** — 找本地 PDF 或从 arXiv 下载，复制到 `output/<id>_en.pdf`
3. **prepare_work** — 解 e-print.tar.gz、识别主 TeX、注入中文 preamble + pdfTeX 兼容兜底
4. **translate_work** — 切 chunk、按 backend 调翻译、备份原文、写回 zh/
5. **build_chinese_pdf** — `latexmk -xelatex`，失败时按已知错误模式自动 fallback 重试
6. **collect_output** — 复制中文 PDF 到 `output/<id>_zh.pdf` 与 `tmp/outbox/`

只有第 4 步需要大模型。其他步骤是 LaTeX 工具链 + 规则代码。

## LaTeX 编译失败的自动 fallback

`src/latex_fallbacks.py` 根据 `latexmk` 日志识别已知问题并打补丁：

| 错误类型 | 补丁 |
|---|---|
| 缺 `ifsym.sty / bbm.sty / bbding.sty` | 注入兼容符号定义 |
| pdfTeX 寄存器未定义（`\pdfminorversion` 等） | **预防性**：在 prepare 阶段紧跟 `\documentclass` 注入 `PDFTEX_COMPAT_BLOCK` |
| `Undefined control sequence` 命中白名单（`\acronym/\Checkmark/\xmark/...`） | 注入 `\providecommand{...}` |
| 译文里 `\macro中文` 边界 | 自动改写为 `\macro{}中文` |
| BibTeX 解析失败 | 优先用上游打包的 `.bbl`（zh 或 source 目录里的现成产物）替换 `\bibliography{...}` 为 `\input{xxx.bbl}` 保留引用；找不到 `.bbl` 时才注释掉整段继续编译 |
| XeTeXglyph 兼容报错 | 注释 `inputenc/fontenc` 等遗留编码包 |

未知错误会输出可手动补齐的 `tlmgr install <pkg>` 建议（如果是缺包）。

## 翻译规则

通用规则保存在 [workflows/arxiv_translation/templates/translation_rules.md](../workflows/arxiv_translation/templates/translation_rules.md)，prepare 阶段会复制到 `tmp/work/<id>/notes/translation_rules.md`。

每篇论文的专用术语在 `tmp/work/<id>/notes/translation_rules.md` 追加。翻译时会把该文件附加到 backend 的 system prompt 后面。

如果某篇论文需要专门术语，优先改单篇规则文件，不要改全局模板。
