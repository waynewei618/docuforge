# Project Agent Notes

- 本项目的长期目标是服务日常和科研工作的文档类任务，逐步形成一个本地文档处理工作台。
- 当前已实现的第一阶段能力是 arXiv 英文论文到中文 PDF：优先下载 arXiv LaTeX 工程，翻译后重新编译并保留原图、公式、引用和版式。
- 后续规划能力包括但不限于：
  - 直接翻译普通 PDF：在没有 arXiv LaTeX 源码时，尽量保留原 PDF 的结构、图片、表格和版式，输出中文 PDF。
  - 根据手稿生成演示文稿：输入手写/图片/扫描件中的流程图、数学推导、实验思路或论文草稿，整理为结构化 PPT。
  - 科研文档整理：从论文、笔记、公式推导、实验结果中生成报告、讲义、摘要、slides 和可继续编辑的中间文档。
  - 多输出格式：按任务需要输出 PDF、Markdown、LaTeX、PPT、Word/Docx、HTML 等格式。
  - 保留 Codex 交互式高质量处理流程，同时支持 DeepSeek API 等本地脚本自动化流程。
- 本项目的 Python 环境使用 conda 环境 `paper_translate`。
- 顶层目录约定：`docs/` 放说明文档，`workflows/` 放可复用流程代码和模板，`workspace/` 放本地运行数据和产物，`papers/` 放当前论文资料集合。
- arXiv 英文 PDF 到中文 PDF 的运行工作区固定为 `workspace/arxiv_translation/`；输入放 `workspace/arxiv_translation/inbox/`，单篇工程放 `workspace/arxiv_translation/work/<arxiv_id>/`，最终中文 PDF 放 `workspace/arxiv_translation/outbox/`。
- 翻译初始化和编译入口为 `workflows/arxiv_translation/scripts/translate_arxiv_pdf.py`。
- Codex 手工翻译流水线继续保留；DeepSeek API 自动翻译入口为 `workflows/arxiv_translation/scripts/deepseek_translate_tex.py`，一键入口为 `workflows/arxiv_translation/scripts/translate_arxiv_pdf.py api-translate <pdf>`，默认读取 `DEEPSEEK_API_KEY`，不把密钥写入项目文件。
- `pip` 和 `conda` 不要写入全局国内源配置；需要国内源时仅在单条命令中临时指定，并取消代理环境变量。
- 临时 pip 国内源示例：
  ```bash
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    conda run -n paper_translate python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <package>
  ```
- 临时 conda 国内源示例：
  ```bash
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    conda install -n paper_translate --override-channels \
    -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main \
    -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r \
    <package>
  ```
- 安装 PyTorch 等命令中明确指定外部下载地址的包时，可以按需保留或临时设置代理。
