# DocuForge

DocuForge 是一个面向日常和科研工作的本地优先文档处理工作台。

当前第一阶段能力是 arXiv 英文论文到中文 PDF：优先下载 arXiv LaTeX 源码工程，翻译自然语言内容，保留原图、公式、引用、表格和论文版式，再重新编译为中文 PDF。

后续规划能力包括：

- 直接翻译普通 PDF；
- 根据手稿、流程图、数学推导和论文草稿生成 PPT；
- 整理论文、实验结果和笔记，生成报告、讲义、摘要和 slides；
- 输出 PDF、Markdown、LaTeX、PPT、Word/Docx、HTML 等多种格式；
- 后端可在 DeepSeek API（离线终端）与 Claude Code subagent 间显式切换。

## 目录结构

```text
docs/                                   # 项目说明、LaTeX 指南、翻译状态
workflows/                              # 可复用工作流代码和模板
  arxiv_translation/
    src/                                # arXiv → 中文 PDF 流水线代码
    templates/                          # 翻译规则和模型提示词
    tmp/                                # 调试缓存：inbox/work/<id>/outbox 等
    output/                             # 最终产物：<id>_en.pdf / <id>_zh.pdf
papers/                                 # 当前样例/研究资料库
  auto_drive_3dgs/                      # 自动驾驶 3DGS 论文集合
```

`papers/`、`workflows/arxiv_translation/tmp/`、`workflows/arxiv_translation/output/` 默认不提交到 Git 仓库。`tmp/` 保留中间产物方便 debug；`output/` 是用户感知的最终输出。

## 主接口

唯一入口（无子命令），从 arXiv ID（或 PDF 路径）到 `output/<id>_en.pdf` + `output/<id>_zh.pdf` 一条命令跑完整条流水线：

```bash
cd workflows/arxiv_translation
conda run -n arxiv_translate python -m src.translate <arxiv_id> [选项]
```

`<arxiv_id>` 接受裸 ID（`2405.17705`）、带版本（`2405.17705v2`）、arXiv URL，或本地 PDF 路径。

### 关键选项

| 选项 | 说明 |
|---|---|
| `--output-dir <dir>` | 产物目录，默认 `./output/`（即 `workflows/arxiv_translation/output/`） |
| `--backend {deepseek,claude}` | 翻译后端，默认 `deepseek`（离线终端走 DeepSeek API）；在 Claude Code 内显式 `--backend claude` 走 `claude -p` subagent，模型由 `CLAUDE_CODE_SUBAGENT_MODEL` 环境变量控制 |
| `--force` | 即使 `output/<id>_zh.pdf` 已存在也强制重做 |
| `--limit-chunks <N>` | 每文件至多翻译 N 个 chunk（调试用） |
| `--main-only` | 只翻译 `--main`（默认 `main_zh.tex`）一个文件 |
| `--no-source` | 不下载 arXiv e-print 源码（仅 PDF 抽取降级） |
| `--json` | 机器可读输出 |

DeepSeek 专属：`--deepseek-{model,base-url,temperature,max-tokens,api-key,timeout,retries,sleep}`。

Claude 专属：`--claude-{model,timeout,retries}`。

### 示例

```bash
# 1. DeepSeek 默认流程
export DEEPSEEK_API_KEY="sk-..."
conda run -n arxiv_translate python -m src.translate 2405.17705

# 2. 用本地 PDF 作输入
conda run -n arxiv_translate python -m src.translate /path/to/paper.pdf

# 3. 自定义输出目录
conda run -n arxiv_translate python -m src.translate 2405.17705 --output-dir /tmp/out

# 4. Claude Code subagent 后端（在 Claude Code 内运行）
conda run -n arxiv_translate python -m src.translate 2405.17705 --backend claude

# 5. 重做（强制重跑翻译+编译）
conda run -n arxiv_translate python -m src.translate 2405.17705 --force
```

幂等：再次跑同一个 ID 默认会跳过；用 `--force` 重做。中间产物保留在 `tmp/work/<id>/`，方便 debug。

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
