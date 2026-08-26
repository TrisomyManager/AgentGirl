---
tags: [domain]
papers: 5
projects: 7
---

# 10 非Token替代架构

## 推荐方案

**短期: Transformer | 中期: Jamba混合 | 远期: Mamba-2 / RWKV-7**

> 前向架构正在快速追赶Transformer，但生态成熟度仍有差距。建议「并轨追踪」策略

## 论文清单

| # | 论文 | 作者 | 年份 | 详情页 |
|---|------|------|:---:|------|
| 1 | RWKV 2305.13048 | Peng et al. | 2023 | [[RWKV-2305.13048]] |
| 2 | Mamba 2312.00752 | Gu & Dao | 2023 | [[Mamba-2312.00752]] |
| 3 | Jamba 2403.19887 | Lieber et al. | 2024 | [[Jamba-2403.19887]] |
| 4 | xLSTM 2405.04517 | Beck et al. | 2024 | [[xLSTM-2405.04517]] |
| 5 | Liquid Time Constant Networks 2006.04439 | Hasani et al. | 2021 | [[Liquid-Time-Constant-Networks-2006.04439]] |


## 开源项目

| 项目 | 仓库 | Stars | License | 核心功能 | 详情页 |
|------|------|-------|---------|---------|------|
| RWKV-LM | BlinkDL/RWKV-LM | ~13k | Apache-2.0 | RWKV全系列模型，CUDA/CPU推理，LoRA支持 | [[RWKV-LM]] |
| RWKV-Runner | josStorer/RWKV-Runner | ~6k | Apache-2.0 | RWKV一键桌面客户端 | [[RWKV-Runner]] |
| mamba | state-spaces/mamba | ~12k | Apache-2.0 | Mamba-1/2官方实现，高效CUDA kernel | [[mamba]] |
| mamba-minimal | johnma2006/mamba-minimal | ~700 | MIT | Mamba纯PyTorch实现(~200行) | [[mamba-minimal]] |
| pymdp | infer-actively/pymdp | ~700 | Apache-2.0 | Active Inference Python实现 | [[pymdp]] |
| ncps | mlech26l/ncps | ~1.5k | Apache-2.0 | Liquid Neural Networks官方实现 | [[ncps]] |
| xLSTM | NX-AI/xlstm | ~4k | Apache-2.0 | xLSTM官方实现，HF集成 | [[xLSTM]] |


## 关联导航

- 返回: [[Home]]
- 核心概念: [[PAD情感模型]] [[OOC检测]] [[LoRA微调]] [[向量检索RAG]] [[BlendShape动画]] [[状态空间模型SSM]]
- 项目文档: [[技术选型调研与对比建议报告]]
