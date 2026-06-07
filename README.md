# DocuForge

DocuForge 是一个面向日常和科研工作的本地优先文档处理工作台。

当前第一阶段能力是 arXiv 英文论文到中文 PDF：优先下载 arXiv LaTeX 源码工程，翻译自然语言内容，保留原图、公式、引用、表格和论文版式，再重新编译为中文 PDF。

后续规划能力包括：

- 直接翻译普通 PDF；
- 根据手稿、流程图、数学推导和论文草稿生成 PPT；
- 整理论文、实验结果和笔记，生成报告、讲义、摘要和 slides；
- 输出 PDF、Markdown、LaTeX、PPT、Word/Docx、HTML 等多种格式；
- 同时保留 Codex 交互式高质量流程和 DeepSeek API 本地自动化流程。

## 目录结构

```text
docs/                         # 项目说明、LaTeX 指南、翻译状态
workflows/                    # 可复用工作流代码和模板
  arxiv_translation/
    scripts/                  # arXiv 翻译 prepare/build/API 脚本
    templates/                # 翻译规则和模型提示词
workspace/                    # 本地运行工作区和产物
  arxiv_translation/
    inbox/                    # 输入 PDF 归档
    work/<arxiv_id>/          # 单篇论文 LaTeX 工程
    outbox/                   # 中文 PDF 和主 TeX 集中输出
papers/                       # 当前样例/研究资料库
  auto_drive_3dgs/            # 自动驾驶 3DGS 论文集合
```

`papers/` 和 `workspace/` 是本地数据目录，默认不提交到 Git 仓库；迁移到新机器后按需重新放入论文 PDF 或重新运行工作流生成。

## 当前可用流程

查看论文列表：

```bash
conda run -n arxiv_translate python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py list
```

初始化一篇 arXiv 论文翻译工程：

```bash
conda run -n arxiv_translate python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py prepare <pdf>
```

编译已翻译的中文 LaTeX 工程：

```bash
conda run -n arxiv_translate python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py build <arxiv_id>
```

使用 DeepSeek API 一键 prepare、翻译并编译：

```bash
export DEEPSEEK_API_KEY="sk-..."
conda run -n arxiv_translate python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py api-translate <pdf>
```

按 arXiv ID 获取英文 PDF 并输出中英双 PDF：

```bash
export DEEPSEEK_API_KEY="sk-..."
conda run -n arxiv_translate python workflows/arxiv_translation/scripts/translate_arxiv_pdf.py translate-id 2405.17705
```

默认产物：

```text
workspace/arxiv_translation/outbox/<arxiv_id>_en.pdf
workspace/arxiv_translation/outbox/<arxiv_id>_zh.pdf
```

## 文档

- [arXiv 翻译流程](docs/arxiv_translation.md)
- [项目目录结构](docs/project_structure.md)
- [LaTeX 与本项目排版环境说明](docs/latex_guide.md)
- [当前翻译进度](docs/translation_status.md)

## 环境约定

- LaTeX 工具链：官方 TeX Live 2026 (`scheme-full`)，装于 `/data/texlive/2026`，通过 `~/.bashrc` 加入 `PATH`；所有 conda 环境直接调用 `xelatex` / `latexmk` / `tlmgr`。不使用 apt 版 TeX Live，不在 conda 环境里装 tectonic 或 texlive。详见 [LaTeX 环境配置](docs/latex_guide.md#本项目-latex-环境配置)。
- Python 能力环境：每能力一个独立 conda 环境，只装该能力的 Python 依赖。当前已有 `arxiv_translate`（arXiv 论文 → 中文 PDF）。
- 不把 API key 写入项目文件；DeepSeek 默认读取 `DEEPSEEK_API_KEY`。
- LaTeX 宏包用 `tlmgr install <pkg>` / `tlmgr update --self --all` 维护。通用的 pip / conda 包管理约定（国内源临时配置、取消代理等）见全局 agent 规则。
