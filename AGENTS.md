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

- 采用「LaTeX 工具链一处共享 + 每能力一个独立 conda 环境」的结构，避免依赖互相污染，让 TeX Live 只装一份。
- LaTeX 共享层：**官方 TeX Live 2026**，scheme-full，装于 `/data/texlive/2026`（用户态，不依赖 apt，不需要 sudo 维护）。
  - 不装在 conda 里，也不用 apt（apt 的 TeX Live 已卸载）。理由：arXiv 论文宏包更新快，conda-forge 与 apt 都跟不上；官方 installer + `tlmgr` 可对 CTAN 任意宏包做单包增量更新。
  - 已在 `~/.bashrc` 中将 `/data/texlive/2026/bin/x86_64-linux` 加入 `PATH`（同步加了 `MANPATH`、`INFOPATH`），所有 shell 与 conda 环境直接调用 `xelatex` / `latexmk` / `tlmgr`，无需 `conda run` 转发。
  - 升级宏包：`tlmgr update --self --all`（首次跑前建议 `tlmgr option repository https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/tlnet/` 切到清华源）。
  - 缺包补装：`tlmgr install <pkg>`。
- Python 能力环境：每个能力一个独立的 conda 环境，命名风格按能力含义统一，只装该能力的 Python 依赖，不要把 TeX Live 装进任何能力环境。
  - 当前已存在：`arxiv_translate`（arXiv 英文论文 → 中文 PDF 流水线的 Python 依赖）。
  - 规划中：`pdf_translate`（普通 PDF 翻译）、`manuscript_to_ppt`（手稿 → PPT）等，按需创建。
  - 不使用 venv 或系统 pip，能力环境一律走 conda。

## 目录与运行约定

- 顶层目录约定：`docs/` 放说明文档，`workflows/` 放可复用流程代码和模板，`workspace/` 放本地运行数据和产物，`papers/` 放当前论文资料集合。
- arXiv 英文 PDF 到中文 PDF 的运行工作区固定为 `workspace/arxiv_translation/`；输入放 `workspace/arxiv_translation/inbox/`，单篇工程放 `workspace/arxiv_translation/work/<arxiv_id>/`，最终中文 PDF 放 `workspace/arxiv_translation/outbox/`。
- 翻译初始化和编译入口为 `workflows/arxiv_translation/scripts/translate_arxiv_pdf.py`。
- Codex 手工翻译流水线继续保留；DeepSeek API 自动翻译入口为 `workflows/arxiv_translation/scripts/deepseek_translate_tex.py`，一键入口为 `workflows/arxiv_translation/scripts/translate_arxiv_pdf.py api-translate <pdf>`，默认读取 `DEEPSEEK_API_KEY`，不把密钥写入项目文件。

## 包管理约定

- `pip` 和 `conda` 不要写入全局国内源配置；需要国内源时仅在单条命令中临时指定，并取消代理环境变量。
- 临时 pip 国内源示例（以 `arxiv_translate` 为例，其他能力环境同理替换环境名）：
  ```bash
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    conda run -n arxiv_translate python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <package>
  ```
- 临时 conda 国内源示例：
  ```bash
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    conda install -n arxiv_translate --override-channels \
    -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main \
    -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r \
    <package>
  ```
- 安装 PyTorch 等命令中明确指定外部下载地址的包时，可以按需保留或临时设置代理。
- LaTeX 宏包用 `tlmgr install <pkg>` / `tlmgr update --self --all` 维护，不通过 conda/pip 安装。
