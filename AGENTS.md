# Project Agent Notes

- 本项目的长期目标是服务日常和科研工作的文档类任务，逐步形成一个本地文档处理工作台。
- 当前已实现的能力是 arXiv 英文论文到中文 PDF：优先下载 arXiv LaTeX 工程，翻译后重新编译并保留原图、公式、引用和版式。
- 后续规划能力包括但不限于：
  - 直接翻译普通 PDF：在没有 arXiv LaTeX 源码时，尽量保留原 PDF 的结构、图片、表格和版式，输出中文 PDF。
  - 根据手稿生成演示文稿：输入手写/图片/扫描件中的流程图、数学推导、实验思路或论文草稿，整理为结构化 PPT。
  - 科研文档整理：从论文、笔记、公式推导、实验结果中生成报告、讲义、摘要、slides 和可继续编辑的中间文档。
  - 多输出格式：按任务需要输出 PDF、Markdown、LaTeX、PPT、Word/Docx、HTML 等格式。
  - 保留 Codex 交互式高质量处理流程，同时支持 DeepSeek API 等本地脚本自动化流程。

## 环境结构

**结构原则**：LaTeX 工具链全机一处共享，全项目共用一个以项目命名的 conda 环境。

- **LaTeX 共享层** — 官方 installer scheme-full，装于 `~/texlive/2026`，`~/.bashrc` 将 `~/texlive/2026/bin/x86_64-linux` 加入 PATH。所有 shell 与 conda 环境直接调 `xelatex` / `latexmk` / `tlmgr`。宏包更新用 `tlmgr update --self --all`，缺包用 `tlmgr install <pkg>`。不用 apt、conda-forge、tectonic 等替代方式。
- **Python 环境** — 全项目共用一个名为 `docuforge` 的 conda 环境，装入所有能力的 Python 依赖。不使用 venv 或系统 pip。

## Agent 自动翻译运行指南（免授权三段式模式）

当用户发出类似"翻译 2006.11239"或"帮我翻译这篇 PDF"等极简指令时，作为 AI 任务助手（Agent），你必须主动将任务拆解为以下三段式流程并在后台静默调度：

1. **第一阶段：准备与导出 (Prepare)**
   进入 `workflows/arxiv_translation` 目录，在命令行运行准备命令：
   ```bash
   conda run -n docuforge python -m src.translate <input> --prepare
   ```
   *此步骤在本地解包并提取待翻译文本段落，输出到 `tmp/work/<arxiv_id>/notes/chunks_to_translate.json`。不调用大模型，无弹窗。*

2. **第二阶段：Agent 内部静默翻译 (Translate)**
   - 读取生成的 `chunks_to_translate.json` 文件；
   - 提取列表里所有 `"translated"` 字段为 `null` 且需要翻译的 chunks；
   - **直接在 Agent 内部（例如使用你的默认模型 gemini-3.1-pro-high）**对这些 chunks 进行中文翻译。**必须直接使用 Agent 原生的大模型网络会话进行翻译，以彻底避免外部进程的弹窗授权拦截**；
   - 翻译完成后，将结果填入 `"translated"` 字段，写回并保存为 `chunks_translated.json`。

3. **第三阶段：译文写回与编译 (Compile)**
   进入 `workflows/arxiv_translation` 目录，在命令行运行编译命令：
   ```bash
   conda run -n docuforge python -m src.translate <input> --compile
   ```
   *此步骤会自动将译文安全写回 TeX，并调用本地 LaTeX 工具链一键编译。*
    - 编译完成后，将生成的 `outputs/arxiv_translation/<arxiv_id>_zh.pdf` 路径链接和编译结果直接呈献给用户即可。

## Agent 手稿生成 PPT 运行指南（免授权三段式模式）

当用户发出类似"把这张手稿做成 PPT"或发送手稿图片等指令时，Agent 必须主动将任务拆解为以下三段式流程并在后台静默调度：

1. **第一阶段：准备 (Prepare)**
   进入 `workflows/manuscript_to_ppt` 目录，在命令行运行准备命令：
   ```bash
   conda run -n docuforge python -m src.generate <image_path> --prepare
   ```
   *此步骤创建工作目录 `tmp/work/<image_id>/`，复制图片并输出元数据。不调用大模型，无弹窗。*

2. **第二阶段：Agent 内部静默生成 Beamer 代码 (Generate)**
   - 读取工作目录中的手稿图片；
   - 读取 `templates/prompt.md` 中的系统提示词规则；
   - **直接在 Agent 内部**使用 Vision LLM 分析手稿，识别独立学术主题，按"一页一主题"原则生成 Beamer frame 代码；
   - 将生成的 LaTeX 代码写入 `tmp/work/<image_id>/frames.tex`。

3. **第三阶段：编译 (Compile)**
   进入 `workflows/manuscript_to_ppt` 目录，在命令行运行编译命令：
   ```bash
   conda run -n docuforge python -m src.generate <image_path> --compile
   ```
   *此步骤自动拼接 `templates/preamble.tex` + `frames.tex`，调用本地 LaTeX 工具链编译，并自动生成每页 PNG 预览图到工作目录。*
   - 如果编译失败，读取错误日志修正 `frames.tex` 后重新运行 `--compile`（最多 3 轮自愈）。

4. **第四阶段：视觉检查 (Visual Check)**
   编译成功后，Agent 必须对生成的 PNG 预览图逐页进行视觉检查：
   - 用 `view_file` 查看 `tmp/work/<image_id>/slide-1.png`、`slide-2.png` 等；
   - 检查项：**公式是否被截断/溢出边界**、**元素是否重叠**、**两列对齐是否协调**、**底部内容是否完整可见**；
   - 若发现问题，修正 `frames.tex`（如调整 vspace、拆分内容、改用 columns 等），然后重新执行第三阶段；
   - 确认无问题后，将 `outputs/manuscript_to_ppt/<image_id>_slides.pdf` 路径链接呈献给用户。
