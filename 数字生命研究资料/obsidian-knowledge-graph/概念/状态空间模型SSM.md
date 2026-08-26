---
tags: [concept, 前沿架构]
aliases: [SSM, State Space Model, 选择性状态空间]
---

# 状态空间模型SSM

## 定义

状态空间模型用微分方程建模序列数据，实现 **O(n) 线性复杂度**。

### 关键演进

```
S4 (2021) -> H3 (2022) -> Hyena (2023) -> Mamba (2023) -> Mamba-2 (2024) -> Jamba (2024)
```

| 架构 | 核心机制 | 推理速度 |
|------|---------|:---:|
| Transformer | 自注意力 O(n^2) | 1x |
| Mamba | 选择性 SSM | **5x** |
| RWKV | Token-shift RNN | **10-100x** |
| Jamba | SSM + Transformer + MoE | **3x+** |

## 相关链接

- 相关概念: [[液态神经网络LNN]], [[Active Inference]]
- 相关论文: [[Mamba-2312.00752]], [[RWKV-2305.13048]]
- 相关项目: [[mamba]], [[RWKV-LM]]

