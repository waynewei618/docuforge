# 同等学力申硕学术论文写作工作台

本目录用于辅助完成文献综述、开题报告、答辩材料和毕业论文写作。默认工作方式是：用 Markdown 与 Codex CLI 等 Agent 反复打磨综述和开题初稿，毕业论文正文逐步迁移到 LaTeX，最终按学校要求导出 Word/PDF。

## 写作源文件

```text
literature_review/src/review.md        # 文献综述主源稿
literature_review/src/references.bib   # 综述和论文共用参考文献
proposal/doc/proposal.md               # 开题报告主源稿
thesis/main.tex                        # 毕业论文 LaTeX 主入口
thesis/chapters/*.tex                  # 毕业论文章节
```

文献综述和开题报告先保持 Markdown，便于 Agent 修改、审阅和做版本 diff。毕业论文阶段优先使用 LaTeX 管理章节、公式、图表、交叉引用和参考文献。Word/Docx 主要作为学校模板套版和最终提交格式。

## 目录结构

```text
guidelines/                  # 学校官方格式、必修环节、系统说明
references/
  papers/                    # 本地论文 PDF 和中文翻译版（gitignored）
  notes/                     # 阅读笔记、结构化摘录、引用素材
literature_review/
  src/                       # 文献综述 Markdown/BibTeX 源稿
  output/                    # 文献综述导出结果
proposal/
  doc/                       # 开题报告 Markdown 源稿
  slides/                    # 开题答辩 PPT/Beamer 源稿和素材
  output/                    # 开题报告和 slides 导出结果
thesis/
  main.tex                   # 毕业论文 LaTeX 主入口
  chapters/                  # 毕业论文章节
  figures/                   # 论文图表和数据
  template/                  # 学校论文模板
archive/                     # 历史开题、综述、选题介绍，仅作参考
```

`scripts/` 暂不保留。主要交互发生在 Codex CLI 等 Agent 中，只有当某类操作需要反复稳定执行时，再新增脚本，例如字数统计、参考文献检查、Markdown 转 docx/PDF、LaTeX 编译包装等。

## 已有材料

- `guidelines/` 已包含文献综述标准格式、研究生必修环节实施细则、开题系统说明和研究生系统说明。
- `references/papers/` 用于本地存放 NeRF、3DGS、HUGS、HUGSIM 等 3D 重建与自动驾驶仿真方向论文，以及对应中文翻译版；PDF 文件默认不提交到 Git。
- `archive/` 已包含历史开题报告、开题答辩 PPT、基于 HUGSIM 的选题介绍等材料。

## Agent 协作流程

1. 写作前先读取 `guidelines/`，确认字数、结构、参考文献数量和提交格式要求。
2. 从本地 `references/papers/` 和 `references/notes/` 组织论文事实、方法对比、引用素材。
3. 参考 `archive/` 中历史材料，但不要直接作为主源稿覆盖当前工作区。
4. 先写 Markdown 草稿，确认结构和论证后，再按学校模板导出 Word/PDF。
5. 毕业论文阶段使用 `thesis/main.tex` 与 `thesis/chapters/` 按章节推进。
