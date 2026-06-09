# Project Agent Notes

- 本项目的长期目标是服务日常和科研工作的文档类任务，逐步形成一个本地文档处理工作台。
- 当前已实现的第一阶段能力是 arXiv 英文论文到中文 PDF：优先下载 arXiv LaTeX 工程，翻译后重新编译并保留原图、公式、引用和版式。
- 后续规划能力包括但不限于：
  - 直接翻译普通 PDF：在没有 arXiv LaTeX 源码时，尽量保留原 PDF 的结构、图片、表格和版式，输出中文 PDF。
  - 根据手稿生成演示文稿：输入手写/图片/扫描件中的流程图、数学推导、实验思路或论文草稿，整理为结构化 PPT。
  - 科研文档整理：从论文、笔记、公式推导、实验结果中生成报告、讲义、摘要、slides 和可继续编辑的中间文档。
  - 多输出格式：按任务需要输出 PDF、Markdown、LaTeX、PPT、Word/Docx、HTML 等格式。
  - 保留 Codex 交互式高质量处理流程，同时支持 DeepSeek API 等本地脚本自动化流程。

## 环境结构

**结构原则**：LaTeX 工具链全机一处共享，每能力一个独立 conda 环境。

- **LaTeX 共享层** — 官方 installer scheme-full，装于 `$HOME/texlive/2026`，通过 `~/.bashrc` 加入 PATH。所有 shell 与 conda 环境直接调 `xelatex` / `latexmk` / `tlmgr`。宏包更新用 `tlmgr update --self --all`，缺包用 `tlmgr install <pkg>`。不用 apt、conda-forge、tectonic 等替代方式。
- **Python 能力环境** — 每个能力一个独立 conda 环境，只装该能力的 Python 依赖。当前已有 `arxiv_translate`（arXiv → 中文 PDF）；规划 `pdf_translate`、`manuscript_to_ppt` 等。不使用 venv 或系统 pip。
