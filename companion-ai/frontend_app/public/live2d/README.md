# Live2D 模型目录

## 测试模型获取

### 官方免费样本模型
下载地址：https://www.live2d.com/en/download/sample-data/

推荐用于测试的模型：
1. **Hiyori** (SDK 4.0样本) - https://cdn.live2d.com/sdk-web/sample/Samples/Resources/Hiyori/
2. **Shizuku** (经典样本)
3. **Haru** (SDK 3.0样本)

### 快速测试步骤

```bash
# 方法1：使用CDN模型（无需下载）
# 在AvatarDisplay.vue中设置modelPath为：
# 'https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/shizuku/shizuku.model.json'

# 方法2：本地下载
cd frontend_app/public/live2d
# 手动下载并解压模型文件到此目录
```

## 目录结构示例

```
live2d/
├── shizuku/              # 测试模型（SDK 2.x）
│   ├── shizuku.model.json
│   ├── shizuku.moc
│   └── textures/
│       └── *.png
│
└── xiaonuan/             # 正式模型（待制作）
    ├── xiaonuan.model3.json
    ├── xiaonuan.moc3
    ├── textures/
    └── motions/
```

## 模型版本兼容性

- **Cubism 2.x**: `.moc` + `.model.json`
- **Cubism 3.x/4.x**: `.moc3` + `.model3.json`
- pixi-live2d-display 0.4.0 支持所有版本
