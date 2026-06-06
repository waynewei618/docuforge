# 项目目录结构

本项目按“本地文档处理工作台”组织目录。arXiv 论文翻译只是第一个工作流，后续会继续加入普通 PDF 翻译、手稿到 PPT、科研文档整理等能力。

## 顶层目录

```text
docs/                         # 面向使用者和维护者的说明文档
workflows/                    # 可复用工作流代码、模板、提示词
workspace/                    # 本地运行数据、缓存、中间工程和输出产物
papers/                       # 当前项目自带的论文资料集合
```

## 当前 arXiv 翻译工作流

```text
workflows/arxiv_translation/
  scripts/
    translate_arxiv_pdf.py     # prepare/list/build/api-translate 入口
    deepseek_translate_tex.py  # DeepSeek API LaTeX 片段翻译
  templates/
    translation_rules.md
    deepseek_system_prompt.md

workspace/arxiv_translation/
  inbox/                       # 输入 PDF 归档副本
  work/<arxiv_id>/             # 单篇论文的完整翻译工程
  outbox/                      # 中文 PDF 和主 TeX 集中输出
  diagnostics/                 # LaTeX 环境测试产物
  agent_logs/                  # 子 agent 或长任务日志
```

## 当前论文资料库

```text
papers/auto_drive_3dgs/
  README.md
  01_scene_reconstruction_dynamic_modeling/
  02_feedforward_generalizable_reconstruction/
  03_sensor_simulation_multimodal/
  04_scene_generation_editing_data/
  05_novel_view_rendering_benchmarks/
  06_appearance_physics_conditions/
  07_closed_loop_systems_evaluation/
  08_efficiency_scaling/
```

这部分是当前自动驾驶 3DGS 论文集合，不是 DocuForge 的核心代码。后续推远程仓库时，可以根据仓库大小和版权风险决定是否保留 PDF 原文，或改成只保留索引和下载脚本。

## 后续新增能力的推荐位置

普通 PDF 翻译：

```text
workflows/pdf_translation/
  scripts/
  templates/
workspace/pdf_translation/
  inbox/
  work/
  outbox/
```

手稿、流程图、数学推导到 PPT：

```text
workflows/slide_generation/
  scripts/
  templates/
workspace/slide_generation/
  inbox/
  work/
  outbox/
```

科研文档整理和多格式输出：

```text
workflows/research_docs/
  scripts/
  templates/
workspace/research_docs/
  inbox/
  work/
  outbox/
```

## 约定

- `workflows/` 放可迁移、可复用的流程代码和模板。
- `workspace/` 放本机运行产生的数据，通常不应全部提交到远程仓库。
- `papers/` 放样例资料或研究语料，是否提交取决于仓库用途和版权约束。
- `docs/` 放人类可读说明、流程文档和状态记录。
- API key 不写入任何项目文件，通过环境变量读取。
