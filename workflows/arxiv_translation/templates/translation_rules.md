# 中文论文翻译规则

## 总体风格

- 使用自然、正式的中文学术论文风格，不逐词硬译。
- 保持原论文技术含义，不擅自补充原文没有的结论。
- 首次出现的核心英文术语可保留括号英文缩写，后文使用统一中文术语。
- 参考文献默认保留英文。

## 必须保留的 LaTeX 内容

- 公式环境和公式编号。
- `\label{...}`、`\ref{...}`、`\cite{...}`、`\url{...}`。
- 图表文件名、图片路径、BibTeX key。
- 方法名、模型名、数据集名、指标名。
- 数值、单位、实验设置。

## 本项目常用术语

| English | 中文 |
|---|---|
| 3D Gaussian Splatting | 三维高斯泼溅（首次写作“三维高斯泼溅（3D Gaussian Splatting, 3DGS）”） |
| Gaussian Splatting | 高斯泼溅 |
| physics-aware | 物理感知 |
| driving scene generation | 驾驶场景生成 |
| pose correction | 位姿校正 |
| vehicle dynamics | 车辆动力学 |
| novel view synthesis | 新视角合成 |
| autonomous driving | 自动驾驶 |
| rendering | 渲染 |
| reconstruction | 重建 |

## 排版偏好

- 优先保留原论文双栏版式和原图。
- 如果双栏阅读性差，可以加宽栏距并开启栏间竖线。
- 不强行复刻 PDF 的每一处换行；以中文可读性和 LaTeX 稳定编译为优先。
- 对复杂大表格，第一版优先保证内容完整和可读。
