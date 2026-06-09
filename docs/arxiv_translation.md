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
| `--output-dir <dir>` | 项目根目录下的 `outputs/arxiv_translation/` | 产物目录 |
| `--force` | — | 即使 `outputs/arxiv_translation/<id>_zh.pdf` 存在也强制重做 |
| `--prepare` | — | 【Agent 异步协作模式】仅解包并导出待翻译的 JSON 文本 |
| `--compile` | — | 【Agent 异步协作模式】仅读取翻译好的 JSON 并编译为 PDF |


## 一键式完整翻译（DeepSeek 后端）

适合离线终端批量/一键完整翻译。要求 `DEEPSEEK_API_KEY` 环境变量（API 直连，无授权弹窗，速度极快）：

```bash
export DEEPSEEK_API_KEY="sk-..."
cd workflows/arxiv_translation
conda run -n docuforge python -m src.translate 2405.17705
```

## Agent 异步协作翻译（免授权三段式模式）

当您在 Antigravity 等 Agent 客户端内进行交互时，如果直接跑一键完整翻译（尤其是调 `agy`），会因高频执行外部 shell 子进程而频繁触发系统安全审计弹窗（例如有 110 个 chunks 时需手动授权 110 次）。

为了提供完美的免授权交互体验，可以采用 **“三段式异步协作流程”**：

1. **准备与导出**：
   在终端运行 `--prepare` 参数：
   ```bash
   conda run -n docuforge python -m src.translate 2006.11239 --prepare
   ```
   此步骤只在本地解包 TeX 并提取待翻译文本，输出到 `tmp/work/<arxiv_id>/notes/chunks_to_translate.json`。**纯本地文件操作，不调用大模型，无任何授权弹窗。**

2. **Agent 内部翻译（零弹窗，灵活指定模型）**：
   主 Agent（如 Antigravity 或是子 subagent）在读取 `chunks_to_translate.json` 后，在 Agent 本身的 Python 上下文中循环调用大模型接口（默认指定 `gemini-3.1-pro-high`）翻译所有文本块，并将译文写入 "translated" 字段后保存为 `chunks_translated.json`。
   **此过程完全在 Agent 的原生 LLM 会话中完成，没有任何外部命令行子进程，零弹窗，且可自由选择模型。**

3. **写回与编译**：
   Agent 在翻译完成后，自动执行 `--compile` 命令：
   ```bash
   conda run -n docuforge python -m src.translate 2006.11239 --compile
   ```
   脚本会将 JSON 中翻译好的内容以倒序安全写回对应的 TeX 源文件（防索引漂移），并调用 `latexmk` 一键编译为中文 PDF。**只执行本地编译命令，零弹窗。**

> 💡 **给 AI 助手的提示**：只要用户下达极简指令（例如“翻译 2006.11239”），你就应当自动识别并按照上述三段式流程，静默地在后台自动完成“导出 -> Agent 内部翻译 -> 写回与编译”的完整循环，为用户提供一键无感翻译体验。

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
