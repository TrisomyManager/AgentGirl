---
tags: [concept, 3D动画]
aliases: [SMPL, SMPL-H, SMPL骨骼]
---

# SMPL人体模型

## 定义

SMPL (Skinned Multi-Person Linear Model) 是参数化 3D 人体模型标准，通过形状参数(beta)和姿态参数(theta)控制人体。

- **SMPL-H**: 扩展版，增加手部关节（52 blendshape）
- **输出格式**: .npz / .fbx / .bvh
- **兼容引擎**: Blender / Unity / Unreal Engine

## SMPL -> Unity/VRM 桥接

```
HY-Motion / MotionLCM -> SMPL-H
  |-> bmlSUP -> Unity blendshape + Mecanim
  |-> ComfyUI-MotionDiff -> FBX -> Blender -> Unity/UE
  |-> BVH -> Unity Humanoid -> VRM
```

## 相关链接

- 相关论文: [[Human-Motion-Generation-Survey-2307.10894]]
- 相关项目: [[HY-Motion-1.0]], [[MotionLCM]], [[bmlSUP]]

