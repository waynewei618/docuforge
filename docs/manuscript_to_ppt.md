# 手稿生成 Beamer PPT 工作流 (manuscript_to_ppt)

```text
输入：手稿图片路径
输出：Beamer PPT (PDF) + 手稿副本（统一重命名并落到 outputs/manuscript_to_ppt/ 目录）
```

## 设计背景与初衷

在学术科研和日常交流中，研究人员经常会手写推导公式、绘制算法框图、记录实验思路。将这些手稿快速、美观地转化为用于演示汇报的 PPT（或 Beamer Slides）通常非常耗时。

`manuscript_to_ppt` 是为此设计的半自动化/Agent 协同工作流，旨在利用大语言模型（LLM/VLM）的视觉与代码生成能力，结合本地 LaTeX 编译工具链，实现从**“手写手稿”到“高质量学术 Beamer Slides”**的一键转换。

---

## 核心设计原则

1. **结构化呈现，去除封面**：
   - 侧重于展示手稿的具体数学推导和逻辑，默认不生成幻灯片封面（Title Slide）。
2. **排版优先级：两列排版优先于缩小字号**：
   - 当单页内容较多或公式密集时，优先使用 LaTeX Beamer 的 `columns` 环境分为左右两列，而不是盲目缩小字号。缩小字号仅作为排版容错的最低优先级考量。
3. **内容关联的文件命名**：
   - 最终输出的 PDF 不使用无意义的图片名（如 `IMG_xxx.pdf`），而是自动扫描生成的 TeX 代码中的 Frame 标题（如 `\begin{frame}{体渲染公式}`），拼合为内容强相关的文件名（如 `体渲染公式_NeRF_训练.pdf`）。
   - 原始手稿图片会自动重命名并复制到输出目录，方便对比与归档。
4. **编译自愈与健壮性**：
   - 支持多达 3 轮的 LaTeX 编译报错-自愈逻辑。当编译失败时，解析编译日志并把具体错误回传给 Agent 进行修复。
5. **视觉检查（Visual Check）**：
   - 编译成功后自动使用系统工具 `pdftoppm` 将 PDF 转为 PNG 预览图，供 Agent 进行视觉合理性检验（例如检查公式是否截断、重叠、文字溢出等），实现闭环优化。

---

## 目录结构

```text
workflows/manuscript_to_ppt/
  src/                                # 流水线代码
    __init__.py
    __main__.py
    generate.py                       # CLI 入口与 Prepare 阶段控制
    compile.py                        # 编译引擎、日志解析、PDF转图片 (pdftoppm)
  templates/
    preamble.tex                      # Beamer 导言区模板（Metropolis主题 + 字体配置）
    prompt.md                         # 核心 Vision LLM 生成提示词
  tmp/                                # 运行时缓存目录（gitignored）
    work/<image_id>/                  # 单次手稿处理的工作空间
      <image_name>.jpg/png            # 原始图片副本
      metadata.json                   # 流程元数据
      frames.tex                      # Agent 生成的 frames 源码
      slides.tex                      # 拼装后的完整 TeX 文件
      slide-1.png, slide-2.png        # 用于视觉检查的预览图
      slides.log, slides.aux ...      # LaTeX 编译中间文件
```

---

## 四段式异步协作工作流

由于命令行进程存在交互授权拦截，本项目采用 **“免授权三段式/四段式异步协作流程”**：

### 阶段 1：准备阶段 (Prepare)
在终端运行 `--prepare` 参数：
```bash
cd workflows/manuscript_to_ppt
conda run -n docuforge python -m src.generate /path/to/handwriting.jpg --prepare
```
- **动作**：创建临时工作目录 `tmp/work/<image_id>`，将原图复制进去，输出 `metadata.json` 记录必要元数据。
- **特点**：无大模型调用，纯本地文件操作，无授权弹窗。

### 阶段 2：Agent 内部生成代码 (Generate)
主 Agent（如 Antigravity 客户端）读取 `metadata.json` 指向的图片和 `templates/prompt.md` 提示词：
- **动作**：使用自身的多模态视觉大模型（如 `gemini-3.5-flash` 或 `gemini-3.1-pro-high`）读取手稿图片，生成 Beamer 帧 LaTeX 源码。
- **特点**：直接将生成的代码写入 `tmp/work/<image_id>/frames.tex`。全在 Agent 内部完成，零外部进程，不触发授权弹窗。

### 阶段 3：编译阶段 (Compile)
在终端运行 `--compile` 参数：
```bash
conda run -n docuforge python -m src.generate /path/to/handwriting.jpg --compile
```
- **动作**：
  1. 将 `templates/preamble.tex` and `tmp/work/<image_id>/frames.tex` 拼接为完整的 `slides.tex`。
  2. 调用本地 `latexmk -xelatex` 编译出 PDF。
  3. 若编译失败，解析日志输出简要错误。
  4. 若编译成功，解析 Frame 标题，将 PDF 和手稿图片重命名复制到 `outputs/manuscript_to_ppt/`，并调用 `pdftoppm` 将 PDF 按页渲染成 PNG 图片存入工作目录。

### 阶段 4：Agent 视觉检查 (Visual Check)
主 Agent 查找工作目录下生成的 `slide-1.png`、`slide-2.png` 等：
- **动作**：使用 Agent 的 `view_file` 工具或内置视觉能力检查渲染出的每一页。
- **核对清单**：
  - 公式是否被幻灯片右边缘截断？
  - 文本、公式、框图是否存在重叠？
  - 多列排版（columns）是否左右对称协调？
  - 底部内容是否超出了页面下边缘？
- **自愈**：如果发现排版问题，直接修改 `frames.tex`（例如加入换行、微调垂直间距、分成多页或改用两列），然后重新调用**阶段 3**进行编译，直到完美。

---

## 关键技术细节与 LaTeX 踩坑记录

在开发 `manuscript_to_ppt` 的过程中，为了确保 LaTeX 编译通过率和排版美观度，我们解决了以下核心技术问题：

### 1. 宏包冲突与中文支持
- **问题**：Beamer 经典主题 `metropolis` 的默认字体配置，在引入 `unicode-math` 宏包和特定中文字体时极易发生内部冲突，导致编译挂起或报错。
- **解决**：在 `preamble.tex` 中移除了 `unicode-math`，转而使用标准 `amsmath`、`amssymb` 配合 `xeCJK` 渲染中文字符，并配置 `Noto Sans CJK SC` 作为中文无衬线字体，实现了公式与中文的平滑兼容。

### 2. 特殊字符与标号渲染
- **问题**：手稿中常见的圆圈数字标号如 ①②③，在默认无衬线字体中缺失字形，导致编译报错或显示为空白。
- **解决**：通过在 `prompt.md` 中约束 Agent 生成规则，要求将这类标号放入 `\textrm{①}` 等 CJK 衬线字体环境渲染；同时严禁生成未定义宏（如 `\xlongequal`，应改用 `\xrightarrow`），大幅提高了初次编译成功率。

### 3. 多列自适应排版
- **问题**：手稿通常包含“左图右式”或“左推导右说明”的结构，单栏容易导致公式溢出。
- **解决**：设计了强大的 Beamer Columns 模板指导。利用 `\begin{columns}[T]` 和 `\begin{column}{0.5\textwidth}` 引导模型进行分栏，极大地改善了高密度幻灯片的视觉效果。

---

## 快速使用

对于开发者或想要测试的 Agent，可以依照以下步骤运行：

1. **前置准备**：
   确保本地已安装 TeX Live 并可通过 PATH 访问 `xelatex` / `latexmk`，并且安装了 `poppler-utils`（包含 `pdftoppm` 用于生成 PNG 预览）。

2. **执行全套流程**：
   ```bash
   # 1. 准备
   conda run -n docuforge python -m src.generate test_manuscript.jpg --prepare
   
   # 2. 模拟 Agent 写出 frames.tex (写入 tmp/work/test_manuscript/frames.tex)
   # 3. 编译
   conda run -n docuforge python -m src.generate test_manuscript.jpg --compile
   ```
