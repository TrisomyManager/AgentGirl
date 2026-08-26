---
tags: [concept, 模型优化]
aliases: [LoRA, Low-Rank Adaptation, QLoRA]
---

# LoRA微调

## 定义

LoRA (Low-Rank Adaptation) 是参数高效微调(PEFT)方法。冻结原始权重，仅训练低秩矩阵，参数量减少 **10,000倍**。

## 核心优势

- 训练速度 2x（配合 [[Unsloth]]）
- 显存减少 50%+
- 可合并/卸载（不增加推理延迟）
- 可为每个角色训练独立 LoRA 权重

## 在本项目中

- **人格微调**: 为不同角色训练独立 LoRA
- **风格控制**: 语气/口癖/回复风格
- Phase 2+ 引入

## 相关链接

- 相关论文: [[LoRA-2106.09685]]
- 相关项目: [[Unsloth]], [[vLLM]]

