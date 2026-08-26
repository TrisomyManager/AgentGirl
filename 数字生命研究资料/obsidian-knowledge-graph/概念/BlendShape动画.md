---
tags: [concept, 角色渲染]
aliases: [BlendShape, 形变混合, 融合变形]
---

# BlendShape动画

## 定义

BlendShape 是通过混合多个预定义形状来驱动面部动画的技术。

- ARKit 标准: 52 个 blendshape
- Live2D 使用类似 Parameter ID 系统
- Unity `SkinnedMeshRenderer` 原生支持
- 论文 [[SAiD-2401.08655]] 直接输出 blendshape 系数

## 在本项目中

- Live2D Parameter ID <-> 情绪标签映射
- TTS 音频能量 -> `setMouthOpenY()` 口型驱动
- V2: SAiD 模型 -> ARKit blendshape -> Live2D 参数

## 相关链接

- 相关概念: [[SMPL人体模型]]
- 相关论文: [[SAiD-2401.08655]]
- 相关项目: [[pixi-live2d-display]]

