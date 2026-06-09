# LaTeX、LaTeX 环境与常见载体中的公式渲染

本文解释三个容易混淆的概念：

- LaTeX 是什么；
- 本项目为什么需要安装完整 LaTeX 环境；
- Markdown、PPT、Word、HTML 里也能写 LaTeX，为什么通常不需要像本项目一样安装 TeX Live。

## 一句话结论

很多软件里说“支持 LaTeX”，实际通常只是支持一小部分 LaTeX 数学公式语法，例如 `$E=mc^2$`。本项目处理的是完整 arXiv 论文源码，需要把 `.tex` 文件、图片、参考文献、双栏版式、宏包、字体和中文排版一起编译成 PDF，所以必须安装完整 LaTeX 发行版和中文字体。

## LaTeX 是什么

LaTeX 是一种基于文本的排版系统。作者写的不是“所见即所得”的页面，而是一份源码：

```latex
\section{Introduction}

We optimize a set of 3D Gaussians by minimizing the rendering loss:
\[
  \mathcal{L} = \lambda_1 \mathcal{L}_1 + \lambda_2 \mathcal{L}_{SSIM}.
\]
```

LaTeX 编译器会把源码排版成 PDF。它擅长：

- 复杂数学公式；
- 论文、书籍、技术报告；
- 自动编号章节、公式、图表；
- 交叉引用；
- 参考文献；
- 多栏版式；
- 大量图片、表格和浮动体；
- 可复现的学术出版排版。

## LaTeX 可以怎样类比

可以把 LaTeX 理解成一种“文档源码语言”。

它和 Markdown 有相似点：都是用纯文本语法描述文档结构，而不是直接拖动页面元素。例如：

| 目标 | Markdown | LaTeX |
|---|---|---|
| 一级标题 | `# Title` | `\section{Title}` |
| 强调 | `**text**` | `\textbf{text}` |
| 图片 | `![](fig.png)` | `\includegraphics{fig.png}` |
| 引用 | 普通链接或脚注 | `\cite{key}` / `\ref{label}` |
| 公式 | `$E=mc^2$` | `$E=mc^2$` 或 `\begin{equation}...\end{equation}` |

它和 Python 也有一点相似：你写的是源码，源码本身不是最终产物，需要由相应工具处理。

```text
Python 源码 .py
  -> Python 解释器执行
  -> 程序结果

LaTeX 源码 .tex
  -> LaTeX 编译器排版
  -> PDF
```

区别是：Python 主要描述程序逻辑，LaTeX 主要描述文档结构和排版逻辑。

因此，“arXiv 论文是 LaTeX 写出来的”可以理解为：作者写了一套 `.tex` 源码工程，里面包含标题、作者、摘要、章节、公式、图片、表格、引用和版式规则。然后这套源码经过 LaTeX 编译器渲染，才得到读者下载到的 PDF。

## LaTeX 环境是什么

“LaTeX 环境”在实践中通常指一整套本地排版工具链，而不只是一个命令。

本项目需要的核心组件包括：

| 组件 | 作用 | 在本项目中由谁提供 |
|---|---|---|
| TeX Live | LaTeX 发行版，包含编译器、宏包、字体配置和辅助工具 | `$HOME/texlive/2026`（官方 installer，scheme-full） |
| XeLaTeX | 支持 Unicode 和系统字体的 LaTeX 引擎，适合中文 PDF | 同上 |
| latexmk | 自动多轮编译，处理引用、目录、BibTeX 等依赖 | 同上 |
| ctex / xeCJK | 中文排版宏包 | 同上（scheme-full 自带） |
| 中文字体 | 中文正文和等宽字体（fandol、华文字体等） | 同上（scheme-full 自带 fandol；系统级 Noto CJK 可补充） |
| BibTeX / biber | 参考文献处理 | 同上 |
| poppler-utils | PDF 文本抽取、检查等辅助工具 | 系统包 `apt install poppler-utils`（与 LaTeX 无关） |

> scheme-full 把所有 CTAN 宏包和 fandol 等中文字体一次装齐，因此「中文字体」「会议模板」「BibTeX」都不需要单独装。具体安装方式见下方「本项目 LaTeX 环境配置」。


本项目里常见编译命令是：

```bash
latexmk -xelatex -interaction=nonstopmode main_zh.tex
```

这不是“渲染一个公式”，而是完整编译一篇论文。

## 本项目为什么必须安装完整 LaTeX

本项目目标是：

```text
输入：arXiv 英文 PDF 或 arXiv LaTeX 源码
输出：尽量保留原图、公式、引用、表格、双栏版式的中文 PDF
```

这意味着我们要处理完整论文工程，例如：

```text
main.tex
sections/introduction.tex
sections/method.tex
figures/pipeline.pdf
tables/results.tex
refs.bib
neurips_2024.sty
```

完整论文源码里会出现：

- `\documentclass{...}`；
- `\usepackage{...}`；
- `\includegraphics{...}`；
- `\cite{...}`、`\ref{...}`、`\label{...}`；
- 自定义命令；
- 学会模板；
- 双栏排版；
- 图表浮动；
- BibTeX 参考文献；
- 中文字体和断行。

这些都需要真正的 LaTeX 编译器和宏包系统。Markdown、Word 或浏览器里的公式渲染器无法替代。

## arXiv 论文源码和 PDF 的关系

很多 arXiv 论文不是作者直接手工编辑 PDF，而是通过这样的链路生成：

```text
LaTeX 工程
  -> main.tex
  -> sections/*.tex
  -> figures/*
  -> tables/*.tex
  -> refs.bib
  -> style/class 文件
  -> LaTeX 编译
  -> PDF
```

PDF 是最终发布产物，LaTeX 工程是生成 PDF 的源码。两者关系类似：

```text
源码代码 -> 编译/运行 -> 程序结果
LaTeX 源码 -> 编译/排版 -> PDF
```

本项目优先下载 arXiv 的 e-print 源码包，就是为了拿到“生成 PDF 的源码”。如果只从 PDF 里抽文字，相当于只拿到了最终截图式产物，再反推结构，质量会差很多。

从 PDF 反推论文结构通常会遇到：

- 段落顺序被双栏打乱；
- 图表和正文关系难以恢复；
- 公式可能被拆碎；
- 表格结构容易丢失；
- 引用编号、公式编号只能靠猜；
- 图片需要额外抽取和重新插入；
- 中文重排后很难保持原论文版式。

所以本项目的核心策略是：能用 LaTeX 源码就不用 PDF 抽取文本。

## Markdown 里的 LaTeX 为什么通常不用安装 LaTeX

Markdown 本身不是 LaTeX。Markdown 常见的是“内嵌 LaTeX 数学公式”：

```markdown
行内公式：$E=mc^2$

块级公式：

$$
\mathcal{L} = \sum_i \| I_i - \hat I_i \|_1
$$
```

渲染 Markdown 时，通常由以下工具把公式画出来：

- MathJax；
- KaTeX；
- GitHub / VS Code / Typora / Obsidian 内置公式渲染器；
- 静态网站构建器中的公式插件。

这些工具只解析数学公式子集，然后在网页里生成 HTML、CSS 或 SVG。它们通常不处理：

- `\documentclass`；
- `\usepackage`；
- `\begin{document}`；
- 复杂论文模板；
- 图片浮动体；
- BibTeX；
- 自动多轮编译；
- 中文论文级排版。

所以 Markdown 里能写 `$...$`，不等于它能编译 arXiv 论文。

## HTML 里的 LaTeX 为什么通常不用安装 LaTeX

HTML 里常见的 LaTeX 支持也是公式渲染。例如网页中写：

```html
<script>
  MathJax.typeset();
</script>

$$
\alpha_i = \prod_{j<i}(1-\sigma_j)
$$
```

浏览器加载 MathJax 或 KaTeX 后，会把公式转成网页元素。这个过程发生在浏览器或前端构建阶段，不需要本机安装 TeX Live。

但 HTML 公式渲染器关注的是“把公式显示出来”，不是“把整篇论文排成 PDF”。它不能直接处理完整 `.tex` 论文工程。

## Word 和 PPT 里的 LaTeX 为什么通常不用安装 LaTeX

Word 和 PowerPoint 里的“LaTeX”通常是指公式输入语法。现代 Office 可以把一部分 LaTeX 数学命令转换成 Office 内部公式对象，例如：

```latex
\frac{a}{b}, \sqrt{x}, \int_0^1 f(x)\,dx
```

这类公式最终变成的是 Office 的公式模型，不是由 LaTeX 编译器排版出来的 PDF。

它适合：

- 在文档或幻灯片里插入单个公式；
- 快速输入分式、积分、矩阵；
- 和 Office 自身排版系统集成。

它不适合：

- 编译 arXiv 论文源码；
- 使用论文模板 `.sty/.cls`；
- 自动管理参考文献；
- 保留 LaTeX 浮动体和交叉引用；
- 复刻双栏会议论文版式。

## “LaTeX 公式语法”和“完整 LaTeX 文档”的区别

| 场景 | 例子 | 需要完整 LaTeX 环境吗 |
|---|---|---|
| Markdown 公式 | `$E=mc^2$` | 通常不需要 |
| HTML 公式 | MathJax / KaTeX | 通常不需要 |
| Word 公式 | Office 公式编辑器 | 通常不需要 |
| PPT 公式 | PowerPoint 公式对象 | 通常不需要 |
| 单个公式转 SVG/PNG | KaTeX、MathJax、matplotlib mathtext | 通常不需要 |
| 完整论文 `.tex` 编译 PDF | arXiv 源码、会议模板、参考文献 | 需要 |
| 中文 LaTeX 论文 PDF | XeLaTeX + ctex + CJK 字体 | 需要 |

核心区别：

```text
公式渲染：只解释一段数学表达式。
论文编译：解释完整文档、宏包、引用、图片、字体、版式和参考文献。
```

## 为什么本项目选择 LaTeX 而不是直接 Markdown/Word/HTML

本项目的目标不是重新写一篇普通中文文档，而是把英文 arXiv 论文变成中文 PDF，并尽量保留论文原貌。

使用 LaTeX 的优势：

- arXiv 原始素材通常就是 LaTeX；
- 原论文图片路径、表格和公式可以直接复用；
- 引用编号和公式编号更容易保持一致；
- 双栏会议论文版式可以保留；
- 复杂公式不需要重新截图或手工排版；
- 编译出来就是学术论文式 PDF。

如果改用 Markdown/Word/HTML，通常会遇到：

- 图表浮动位置需要重做；
- 参考文献和交叉引用要重新管理；
- 双栏论文版式难以复刻；
- 大表格和多行公式容易坏；
- PDF 输出质量不稳定；
- arXiv 源码里的宏包和自定义命令无法直接使用。

## 图片、表格和双栏版式是谁负责的

如果使用 arXiv LaTeX 源码，原论文图片通常已经在工程目录中，例如：

```text
figures/pipeline.pdf
figures/result.png
assets/overview.jpg
```

正文里会通过 LaTeX 命令引用它们：

```latex
\begin{figure}
  \centering
  \includegraphics[width=\linewidth]{figures/pipeline.pdf}
  \caption{Overview of the proposed method.}
  \label{fig:pipeline}
\end{figure}
```

翻译时，我们通常只翻译 `\caption{...}` 里的图题，不改 `\includegraphics{...}` 的图片路径。这样重新编译时，LaTeX 会自动把原图放回 PDF。

如果某个早期 PDF 看起来“没有插入原论文图片”，常见原因是走了 PDF 抽取/重排路径，或者源码里图片路径、模板、编译依赖没有被正确保留。使用 arXiv LaTeX 工程可以显著减少这类问题。

双栏版式也不是大模型对齐出来的，而是 LaTeX 模板和编译器排版出来的。例如会议模板可能设置：

```latex
\documentclass[twocolumn]{article}
```

或在模板 `.cls/.sty` 里定义双栏。LaTeX 会把正文作为连续文本流排入左栏和右栏。左右两栏在视觉上同一水平线出现，不表示它们在语义上是同一行；那只是页面排版结果。

如果希望某些内容左右明确成组或加框，需要用 LaTeX 的结构表达，例如：

- `figure*` / `table*` 跨双栏；
- `minipage` 并排内容；
- `tcolorbox` / `mdframed` 文本框；
- `tabular` 表格；
- 手工调整浮动体位置。

这类排版结构可以由人工或 Codex 辅助修改，但最终位置仍由 LaTeX 编译器决定。大模型负责改源码，不负责直接“画 PDF 页面”。

## 本项目中的实际分工

当前项目里有两层工作：

1. 翻译层：
   - Codex 会话翻译；
   - 或 DeepSeek API 本地脚本翻译。

2. 排版层：
   - `python -m src.translate <arxiv_id>` 跑完整条流水线（包含初始化）；
   - 修改 `workflows/arxiv_translation/tmp/work/<arxiv_id>/zh/` 下的 LaTeX；
   - 主流水线自动调 latexmk 编译，缓存留在 `tmp/work/<arxiv_id>/build_zh/`；
   - 输出中文 PDF 到 `outputs/arxiv_translation/` 和源 PDF 同目录。

还有一层目录组织：

```text
workflows/arxiv_translation/tmp/work/<arxiv_id>/
  input.pdf        # 本项目接收的英文 PDF 副本
  source/          # arXiv 原始英文 LaTeX 工程
  zh/              # 中文 LaTeX 工程，后续可继续编辑
  build_zh/        # 中文编译中间产物和本次 PDF
  notes/           # 翻译规则、日志、任务说明
  api_backups/     # DeepSeek API 脚本改写前的备份
```

其中最重要的是：

- `source/`：原始英文源码，尽量不要改；
- `zh/`：中文翻译工程，翻译和修复都在这里做；
- `build_zh/`：编译产生的中间文件，不作为主要编辑对象；
- `outputs/`（位于项目目录下的 `outputs/arxiv_translation/`）：用户感知的最终产物，每篇出 `<id>_<title_slug>.pdf` 和 `<id>_<title_slug>_zh.pdf`。

简化流程：

```text
英文 PDF / arXiv ID
  -> 下载 arXiv LaTeX 源码
  -> 复制为中文 LaTeX 工程
  -> 翻译标题、摘要、正文、图表标题
  -> XeLaTeX 编译
  -> 中文 PDF
```

更贴近本项目脚本的完整流程是：

```text
本地英文 PDF
  -> 从文件名识别 arXiv ID
  -> 到 arXiv 下载 e-print 源码包
  -> 解包成 LaTeX 工程
  -> 复制一份到 workflows/arxiv_translation/tmp/work/<arxiv_id>/zh/
  -> 对其中英文标题、摘要、正文、图表标题做中文翻译
  -> 保留公式、图片、引用、表格、模板、BibTeX key
  -> 用 XeLaTeX / latexmk 重新编译
  -> 生成中文 PDF
  -> 复制到 outputs/arxiv_translation/ 和源 PDF 同目录
```

这里的关键点是：本项目不是直接修改 PDF，而是尽量修改“生成 PDF 的源码”。arXiv 论文通常是作者用 LaTeX 写出来的源码工程，经过 LaTeX 编译器渲染后才成为 PDF。本项目把英文 LaTeX 工程复制为中文 LaTeX 工程，翻译其中的自然语言文本，再重新编译成中文 PDF。

`workflows/arxiv_translation/tmp/work/<arxiv_id>/zh/` 会一直保留。它是中文 LaTeX 工程目录，不是临时缓存。后续如果要润色翻译、修复排版、重新生成 PDF，都应直接修改这个目录下的 `.tex` 文件，然后重新运行 build。

## 哪些步骤需要大模型

本项目大部分流程是确定性的本地程序工作。真正需要大模型的是翻译，以及少量 LaTeX 修复和中文润色。

| 步骤 | 是否需要大模型 | 说明 |
|---|---|---|
| 本地英文 PDF | 不需要 | 文件已经在项目目录中 |
| 从文件名识别 arXiv ID | 不需要 | 正则匹配文件名中的 `2308.04079` 这类 ID |
| 到 arXiv 下载 e-print 源码包 | 不需要 | 普通网络下载 |
| 解包成 LaTeX 工程 | 不需要 | `tar/gzip` 等本地解包 |
| 复制到 `workflows/arxiv_translation/tmp/work/<arxiv_id>/zh/` | 不需要 | 文件复制 |
| 翻译英文标题、摘要、正文、图表标题 | 需要 | 需要 Codex、DeepSeek API 或人工翻译 |
| 保留公式、图片、引用、表格、模板、BibTeX key | 主要不需要 | 规则可由脚本控制，但大模型翻译时必须遵守 |
| 编译 LaTeX 工程 | 不需要 | `latexmk` / `xelatex` 完成 |
| 编译失败后分析日志并修复 | 可选需要 | 简单问题可人工修；复杂宏包、语法问题适合 Codex 辅助 |
| 生成中文 PDF | 不需要 | 编译产物 |
| 复制到 outbox 和源目录 | 不需要 | 文件复制 |

因此可以这样理解：

```text
工程流水线：脚本和 LaTeX 环境负责。
语言翻译：Codex、DeepSeek API 或人工负责。
编译修复：脚本先报错，Codex 或人工根据日志修。
```

DeepSeek API 模式里，大模型主要参与 `workflows/arxiv_translation/tmp/work/<arxiv_id>/zh/` 中英文段落的翻译。Codex 模式里，大模型还可以额外参与 LaTeX 结构修复、术语统一、质量抽查和重新编译。

## Codex 流水线和 DeepSeek API 流水线的区别

本项目保留两条翻译流水线。

Codex 流水线：

```text
prepare
  -> Codex 在当前会话中阅读 LaTeX
  -> Codex 翻译、修复、编译、抽查
  -> build
```

特点：

- 适合质量优先；
- 适合处理复杂 LaTeX 报错；
- 可以边翻译边根据 PDF 效果调整；
- 需要 Codex 会话持续参与。

DeepSeek API 流水线：

```text
prepare
  -> 本地脚本切分 LaTeX 段落
  -> 调用 DeepSeek API 翻译片段
  -> 写回 zh/ 工程
  -> build
```

特点：

- 适合批量先生成中文初稿；
- 不需要 Codex 一直盯着；
- 大模型主要只做段落翻译；
- 编译失败或排版异常时，仍可能需要 Codex 或人工介入修复。

两条流水线共用同一个工程结构，也就是说最终都会修改：

```text
workflows/arxiv_translation/tmp/work/<arxiv_id>/zh/
```

也都会通过：

```bash
conda run -n docuforge python -m src.translate <arxiv_id>  # 注：cd workflows/arxiv_translation 后运行
```

生成中文 PDF。

## 给 Codex 或 DeepSeek 下 prompt 的边界

翻译 prompt 的目标不是让大模型“重新排版一篇论文”，而是让它只改自然语言，尽量保留 LaTeX 结构。

好的 prompt 应明确：

- 翻译标题、摘要、正文、图表标题；
- 保留公式、引用、标签、图片路径、BibTeX key；
- 保留方法名、模型名、数据集名、指标名；
- 参考文献默认不翻译；
- 不擅自增删原文结论；
- 翻译完成后重新编译并修复报错。

Codex 流水线可使用类似提示：

```text
请按 workflows/arxiv_translation/tmp/work/<arxiv_id>/notes/translation_rules.md 翻译
workflows/arxiv_translation/tmp/work/<arxiv_id>/zh 中的 LaTeX 源码。

要求：
1. 保留公式、引用、label/ref/cite/url、图片路径、表格结构和 BibTeX key；
2. 标题、摘要、正文、图表标题翻译成中文学术论文风格；
3. 方法名、模型名、数据集名、指标名保留英文或采用约定术语；
4. 参考文献默认保留英文；
5. 翻译完成后运行 build；
6. 若编译失败，请根据日志修复，直到中文 PDF 成功生成。
```

DeepSeek API 流水线的系统提示词在：

```text
workflows/arxiv_translation/templates/deepseek_system_prompt.md
```

单篇论文术语规则在：

```text
workflows/arxiv_translation/tmp/work/<arxiv_id>/notes/translation_rules.md
```

本地脚本会把单篇规则追加到系统提示词后面，再发送需要翻译的 LaTeX 片段。

## 本项目 LaTeX 环境配置

本项目把 LaTeX 工具链当作**全局共享资源**，不和任何 conda 能力环境绑在一起：

```text
LaTeX 工具链（一份，全局共享）
  └─ $HOME/texlive/2026          ← 官方 install-tl 装的 TeX Live 2026 scheme-full
  └─ 通过 PATH 暴露给所有 shell 和 conda 环境

Python 环境（全局共享，以项目命名）
  └─ docuforge                    ← 本项目的所有 Python 依赖（pymupdf / pypdf / rich / ...）
```

任何能力环境里都**不要装 TeX Live 或 tectonic 这类 LaTeX 引擎**。脚本通过 PATH 直接调 `xelatex` / `latexmk` / `tlmgr` 即可。

### 为什么选官方 installer，不选 apt 或 conda

LaTeX 工具链至少有三种装法，各有优缺点：

| 维度 | apt（`texlive-*`） | conda-forge（`texlive-core`、`tectonic`） | 官方 install-tl（**本项目采用**） |
|---|---|---|---|
| TeX Live 版本 | 跟 Ubuntu 发行版，可能落后 1–2 年 | conda-forge 跟得相对慢 | 永远最新，`tlmgr` 可滚动升级 |
| 宏包完整性 | `texlive-full` 较全；按子包装常缺细分宏包 | **明显不全**，arXiv 论文常报缺包 | scheme-full **覆盖 CTAN 全部宏包** |
| 单包补装 | apt 粒度粗，小宏包常无独立包 | conda-forge 上很多宏包根本没打包 | `tlmgr install <pkg>`，CTAN 任意单包 |
| 权限 | 需要 `sudo` | 用户态 | **用户态**，不动系统 |
| 多版本共存 | 不行 | 不行 | 可（`$HOME/texlive/2024`、`$HOME/texlive/2026` 并存） |
| 跟其他系统包耦合 | 升级时偶尔被联动卸载/降级 | 不耦合系统 | **完全独立**，系统升级不动它 |
| 首装时间 | 几分钟（apt 缓存） | 几分钟 | 30–120 分钟（要下 4000+ 宏包） |
| 卸载干净 | `apt purge` | `conda remove` | `rm -rf` 安装目录 |

对本项目（编译近 1–2 年的 arXiv 论文，宏包更新非常快）来说，决定性因素是**宏包完整性 + tlmgr 单包增量更新能力**——apt 和 conda 都在这两点上明显不足。代价是首装时间长，但只需要付一次。

### 安装步骤（本项目实际使用）

#### 1. 卸载历史 apt TeX Live（如果有）

```bash
# 先 dry-run，确认不会牵连关键工具
sudo apt-get -s purge 'texlive-*' 'latex-cjk-*' tex-common latexmk lmodern fonts-lmodern tipa 2>&1 \
  | grep -E "^(Remv|Purg)" | head -40

# 确认无意外后正式卸载
sudo apt-get purge -y 'texlive-*' 'latex-cjk-*' tex-common latexmk lmodern fonts-lmodern tipa
sudo apt-get autoremove -y
sudo rm -rf /var/lib/texmf /etc/texmf
hash -r
```

#### 2. 用官方 installer 装 scheme-full 到 `$HOME/texlive/2026`

> 本机安装在 `~` 下，可直接照做。若后续换到其他盘，只需把以下命令里的 `TEXLIVE_ROOT` 改为目标路径。

```bash
# 取消代理，走清华源下 installer
export TEXLIVE_ROOT="$HOME/texlive/2026"
cd /tmp
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  wget https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/tlnet/install-tl-unx.tar.gz
tar -xzf install-tl-unx.tar.gz
cd install-tl-2*/

# 非交互安装 scheme-full 到 $HOME/texlive/2026
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  ./install-tl \
  -repository https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/tlnet/ \
  -scheme scheme-full \
  -no-interaction \
  -texdir "$TEXLIVE_ROOT" \
  -texuserdir "$HOME/.texlive2026"
```

清华源走得满的话 1.5–2 小时完成（5000+ 宏包，约 10G）。中途断网可以重跑同一条命令，installer 支持续装。

#### 3. 把 TeX Live 加入 PATH

```bash
cat >> ~/.bashrc <<'EOF'

# TeX Live 2026 (官方 installer 装于 $TEXLIVE_ROOT)
export PATH="$TEXLIVE_ROOT/bin/x86_64-linux:$PATH"
export MANPATH="$TEXLIVE_ROOT/texmf-dist/doc/man:$MANPATH"
export INFOPATH="$TEXLIVE_ROOT/texmf-dist/doc/info:$INFOPATH"
EOF

source ~/.bashrc
```

#### 4.（可选）把 tlmgr 默认源切到清华

```bash
tlmgr option repository https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/tlnet/
```

以后 `tlmgr install` / `tlmgr update --self --all` 都自动走国内源。

#### 5. 验证

```bash
which xelatex latexmk tlmgr
xelatex --version | head -1
tlmgr --version | head -3
```

应该看到：

```text
$HOME/texlive/2026/bin/x86_64-linux/xelatex
$HOME/texlive/2026/bin/x86_64-linux/latexmk
$HOME/texlive/2026/bin/x86_64-linux/tlmgr
XeTeX 3.141592653-2.6-0.999998 (TeX Live 2026)
tlmgr revision ...
TeX Live ... version 2026
```

### 安装 Python 共用环境

LaTeX 工具链装好后，再准备 `docuforge` conda 环境（只装 Python 依赖）：

```bash
# 创建环境
conda create -n docuforge python=3.11 -y

# 国内源临时装包（不写入全局配置）
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  conda run -n docuforge python -m pip install \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  pymupdf pypdf rich pydantic jinja2
```

**禁止**在 `docuforge` 环境里装 `tectonic` / `texlive-core` 等 LaTeX 包——LaTeX 只走 `$HOME/texlive/2026` 这一份。

### 验证完整链路

```bash
conda run -n docuforge python -m src.translate  # 注：cd workflows/arxiv_translation 后运行
```

输出应包含：

```text
conda:    /home/.../miniconda3/bin/conda
python:   /home/.../miniconda3/envs/docuforge/bin/python
xelatex:  $HOME/texlive/2026/bin/x86_64-linux/xelatex
latexmk:  $HOME/texlive/2026/bin/x86_64-linux/latexmk
pdftotext: /usr/bin/pdftotext
ctex.sty: $HOME/texlive/2026/texmf-dist/tex/latex/ctex/ctex.sty
xeCJK.sty: $HOME/texlive/2026/texmf-dist/tex/xelatex/xecjk/xeCJK.sty
```

关键点：`python` 来自 conda 共享环境，`xelatex` / `latexmk` / `*.sty` 全部来自 `$HOME/texlive/2026`，**两层职责分清**。

### 日常维护

- **缺宏包**（编译报 `Package xxx not found`）：`tlmgr install <pkg>`
- **更新宏包**（拿最新版本）：`tlmgr update --self --all`
- **查宏包在哪**：`kpsewhich <pkg>.sty`
- **看已装哪些宏包**：`tlmgr list --only-installed`
- **完全卸载 TeX Live**：`rm -rf $HOME/texlive/2026 $HOME/.texlive2026`，然后从 `~/.bashrc` 删掉 PATH 三行

`tlmgr` 完全用户态，不需要 sudo。


## 本项目常用 LaTeX 命令

跑完整条流水线（下载源码/翻译/编译/落产物，单条命令）：

```bash
cd workflows/arxiv_translation
conda run -n docuforge python -m src.translate <arxiv_id>
# 或用本地 PDF 作输入：
conda run -n docuforge python -m src.translate /path/to/paper.pdf
```

直接在某篇中文工程目录中手动编译（用于调试 LaTeX 问题）：

```bash
cd workflows/arxiv_translation/tmp/work/<arxiv_id>/zh
latexmk -xelatex -interaction=nonstopmode -halt-on-error main_zh.tex
```

清理 LaTeX 中间产物：

```bash
cd workflows/arxiv_translation/tmp/work/<arxiv_id>/zh
latexmk -C
```

本项目推荐使用统一入口 `python -m src.translate <input>`，它会跑完整条流水线（下载/翻译/编译/落产物），把 PDF 复制到 `outputs/arxiv_translation/` 和源 PDF 同目录。手动 `latexmk` 仅用于调试。

## 什么时候需要安装 LaTeX

需要安装完整 LaTeX 的情况：

- 要编译 `.tex` 文件成 PDF；
- 要使用 arXiv 源码；
- 要使用会议模板；
- 要处理 BibTeX 参考文献；
- 要生成中文论文 PDF；
- 要复用原论文图片、表格、交叉引用和版式。

通常不需要安装完整 LaTeX 的情况：

- 只在 Markdown 里显示几个公式；
- 只在 HTML 页面中显示数学公式；
- 只在 Word/PPT 里插入公式；
- 只需要把公式显示在网页或笔记软件里；
- 不需要处理完整 `.tex` 文档。

## 常见误解

### 误解 1：能写 `$...$` 就等于支持 LaTeX

不准确。多数场景只是支持 LaTeX 数学公式子集，不支持完整 LaTeX 文档。

### 误解 2：LaTeX 是一种 PDF 格式

不准确。LaTeX 是源码和排版系统。PDF 是编译产物。

### 误解 3：安装 LaTeX 后翻译会自动完成

不准确。LaTeX 只负责排版和编译，不负责高质量翻译。翻译由 Codex、DeepSeek API 或人工完成。

### 误解 4：Markdown 可以替代本项目的 LaTeX 流程

多数情况下不适合。Markdown 适合轻量文档，不适合复刻完整 arXiv 论文工程。

## 本项目推荐记法

在本项目讨论时，建议区分这几个词：

- `LaTeX 公式`：例如 `$E=mc^2$`，只是一段数学表达式。
- `LaTeX 源码`：完整 `.tex` 文件和相关章节文件。
- `LaTeX 工程`：`.tex`、图片、表格、`.bib`、模板、宏包组成的论文目录。
- `LaTeX 环境`：TeX Live、XeLaTeX、latexmk、中文宏包和字体。
- `LaTeX 编译`：把完整工程变成 PDF 的过程。

一句话判断：

```text
如果只是显示公式，通常不需要安装完整 LaTeX。
如果要把 arXiv 论文源码编译成中文 PDF，就需要完整 LaTeX 环境。
```
