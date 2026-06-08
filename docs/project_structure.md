# 项目目录结构

本项目按"本地文档处理工作台"组织目录。arXiv 论文翻译只是第一个工作流，后续会继续加入普通 PDF 翻译、手稿到 PPT、科研文档整理等能力。

## 顶层目录

```text
docs/                         # 面向使用者和维护者的说明文档
workflows/                    # 可复用工作流代码、模板、运行缓存、最终产物
papers/                       # 当前项目自带的论文资料集合
```

每个 workflow 自包含：代码、模板、运行时缓存、最终产物都放在 `workflows/<name>/` 下，便于整体迁移/清理。

## 当前 arXiv 翻译工作流

```text
workflows/arxiv_translation/
  src/                              # 流水线代码
    translate.py                    # CLI 入口（python -m src.translate <input>）
    pipeline.py                     # 流水线编排：prepare → translate → build → collect
    tex_translator.py               # chunk 切分 / 文件遍历 / 备份 / 调 backend
    backends.py                     # DeepSeekBackend + ClaudeCodeBackend + factory
    latex_fallbacks.py              # LaTeX 兼容兜底 / 编译失败自动 patch
  templates/
    translation_rules.md            # 通用术语规则
    deepseek_system_prompt.md       # 翻译 backend 的 system prompt
  tmp/                              # 调试缓存（gitignored）
    inbox/                          # 输入 PDF 归档副本
    work/<arxiv_id>/                # 单篇论文的完整工程：source/zh/notes/build_zh/...
    outbox/                         # build 阶段的调试归档
    diagnostics/  agent_logs/       # LaTeX 诊断 / 子 agent 日志
  output/                           # 最终产物（gitignored）：<id>_en.pdf / <id>_zh.pdf
```

`tmp/` 与 `output/` 都不进 git。`tmp/` 是"出问题能复现/调试"的地方，`output/` 是用户感知的最终输出。

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

每个新能力沿用同样的「自包含」结构：

```text
workflows/<capability_name>/
  src/                  # 代码（python -m src.<entry>）
  templates/            # 提示词、规则、配置模板
  tmp/                  # 运行时缓存（gitignored）
  output/               # 最终产物（gitignored）
```

例如：

- `workflows/pdf_translation/` — 普通 PDF 翻译
- `workflows/slide_generation/` — 手稿/流程图 → PPT
- `workflows/research_docs/` — 科研文档整理和多格式输出

## 约定

- `workflows/<name>/src/` 放可迁移、可复用的流程代码；入口统一是 `python -m src.<file>`（在 `workflows/<name>/` 目录下执行）。
- `workflows/<name>/tmp/` 与 `output/` 放本机运行数据，不提交远程仓库。
- `papers/` 放样例资料或研究语料，是否提交取决于仓库用途和版权约束。
- `docs/` 放人类可读说明、流程文档和状态记录。
- API key 不写入任何项目文件，通过环境变量读取（DeepSeek 走 `DEEPSEEK_API_KEY`；Claude Code subagent 直接继承当前 session 认证）。
