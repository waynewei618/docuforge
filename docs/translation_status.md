# 翻译进度

更新时间：2026-06-07

## 当前策略

- 有发表信息论文优先级已完成；剩余任务全部来自 `未查到正式发表信息/`。
- 每篇优先使用 arXiv LaTeX 源码，保留原图、公式、引用和表格结构。
- 翻译后端通过 `--backend {deepseek,claude}` 显式指定：离线终端走 DeepSeek API，Claude Code 内显式走 `--backend claude` 调 `claude -p` subagent。
- 中文 PDF 同时落在 `workflows/arxiv_translation/output/<id>_zh.pdf` 与源英文 PDF 同目录。

## 当前状态

- 总论文数：105 篇
- 已翻译并编译：98 篇
- 已 prepare 但未编译：0 篇
- 尚未 prepare：7 篇

分组进度：

| 分组 | 总数 | 已编译 | 已 prepare 待编译 | 未 prepare |
|---|---:|---:|---:|---:|
| 有发表信息 | 44 | 44 | 0 | 0 |
| 未查到正式发表信息 | 61 | 54 | 0 | 7 |
| 合计 | 105 | 98 | 0 | 7 |

产物检查：

- `workflows/arxiv_translation/output/` 中中文 PDF：98 份（注：本次重构后路径从原 `workspace/.../outbox/` 迁来）。
- 源英文 PDF 同目录中文 PDF：98 份。

## 已完成 ID

有发表信息：

```text
2308.04079, 2311.18561, 2312.07920, 2411.11921, 2411.15355,
2411.15582, 2412.15447, 2502.14235, 2506.22099, 2507.12137,
2409.12753, 2503.20168, 2504.00437, 2411.16816, 2503.10170,
2507.18713, 2510.12901, 2603.06061, 2605.22809, 2405.14475,
2410.13571, 2411.19292, 2411.19548, 2503.10604, 2506.07826,
2506.13558, 2506.22800, 2507.18473, 2509.19937, 2602.21333,
2403.20079, 2405.17705, 2408.15242, 2502.15635, 2405.20323,
2506.05280, 2507.03886, 2602.13549, 2604.03462, 2605.16925,
2412.01718, 2412.15550, 2506.04218, 2605.01995
```

未查到正式发表信息：

```text
2401.01339, 2403.20032, 2407.16600, 2408.16760, 2409.10041,
2411.15482, 2503.06744, 2503.08217, 2503.12001, 2504.00763,
2508.12015, 2508.15376, 2510.09364, 2510.25173, 2511.06632,
2511.19235, 2603.12647, 2510.19578, 2510.24734, 2601.15951,
2603.07552, 2603.08254, 2605.04435, 2605.09688, 2605.11594,
2404.02410, 2501.13971, 2503.08317, 2503.11731, 2506.01379,
2509.17390, 2603.14763, 2405.18416, 2501.00601, 2506.21520,
2507.21872, 2507.23683, 2508.20471, 2509.19296, 2509.20251,
2510.02469, 2511.21113, 2512.22706, 2602.24096, 2605.13591,
2605.25373, 2406.18198, 2407.02598, 2407.02945, 2409.02382,
2412.05256, 2502.21093, 2510.12282, 2606.03909
```

## 剩余任务

以下 7 篇尚未完成，均尚未 prepare：

| ID | 状态 | 源 PDF |
|---|---|---|
| `2503.09464` | 未 prepare | `papers/auto_drive_3dgs/05_novel_view_rendering_benchmarks/未查到正式发表信息/2503.09464_Hybrid_Rendering_for_Multimodal_Autonomous_Driving_Merging_Neural_and_Physics-Based_Simulation.pdf` |
| `2601.07540` | 未 prepare | `papers/auto_drive_3dgs/05_novel_view_rendering_benchmarks/未查到正式发表信息/2601.07540_Enhancing_Novel_View_Synthesis_via_Geometry_Grounded_Set_Diffusion.pdf` |
| `2604.05908` | 未 prepare | `papers/auto_drive_3dgs/06_appearance_physics_conditions/未查到正式发表信息/2604.05908_Appearance_Decomposition_Gaussian_Splatting_for_Multi-Traversal_Reconstruction.pdf` |
| `2605.21032` | 未 prepare | `papers/auto_drive_3dgs/06_appearance_physics_conditions/未查到正式发表信息/2605.21032_Towards_Physically_Consistent_4D_Scene_Reconstruction_for_Closed-loop_Autonomous_Driving_Simulation.pdf` |
| `2502.13144` | 未 prepare | `papers/auto_drive_3dgs/07_closed_loop_systems_evaluation/未查到正式发表信息/2502.13144_RAD_Training_an_End-to-End_Driving_Policy_via_Large-Scale_3DGS-based_Reinforcement_Learning.pdf` |
| `2503.18108` | 未 prepare | `papers/auto_drive_3dgs/07_closed_loop_systems_evaluation/未查到正式发表信息/2503.18108_Unraveling_the_Effects_of_Synthetic_Data_on_End-to-End_Autonomous_Driving.pdf` |
| `2604.28111` | 未 prepare | `papers/auto_drive_3dgs/07_closed_loop_systems_evaluation/未查到正式发表信息/2604.28111_GSDrive_Reinforcing_Driving_Policies_by_Multi-mode_Future_Trajectory_Probing_with_3D_Gaussian_Splatting_Enviro.pdf` |

## 常用命令

> 入口统一：`cd workflows/arxiv_translation`，然后 `python -m src.translate <arxiv_id> [选项]`。无子命令，整条流水线（下载/翻译/编译/落产物）一条命令跑完。

DeepSeek 后端（默认，离线终端）：

```bash
export DEEPSEEK_API_KEY="sk-..."
cd workflows/arxiv_translation
conda run -n arxiv_translate python -m src.translate <arxiv_id>
```

Claude Code subagent 后端（在 Claude Code 内）：

```bash
cd workflows/arxiv_translation
conda run -n arxiv_translate python -m src.translate <arxiv_id> --backend claude
```

完整接口与选项见 [arxiv_translation.md](arxiv_translation.md) 与项目根 [README.md](../README.md)。
