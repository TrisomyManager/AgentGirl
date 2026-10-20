# Live2D 模型目录

## 随应用提供的资源

`shizuku/` 已包含模型本体、6 张贴图、表情、物理/姿态、动作与音效；全部从本地加载。
示例模型的动作自带日语音效，应用在 Live2D 初始化时关闭动作音效，语音统一由聊天/通话播放器处理。
请将此目录整体纳入构建，不能只保留 `shizuku.model.json`。缺失的静态文件在 Vite 开发环境中可能返回页面 HTML，继而造成 `Invalid moc data` 或贴图加载失败。

- 资源来源：[pixi-live2d-display 的 Shizuku 示例](https://github.com/guansss/pixi-live2d-display/tree/31317b37d5e22955a44d5b11f37f421e94a11269/test/assets/shizuku)。仅引入该模型引用的资源，未导入外部项目源码。
- 上游版本：`31317b37d5e22955a44d5b11f37f421e94a11269`；`asset-manifest.json` 记录资源大小与 SHA-256。
- 版权归 Live2D 示例素材权利人所有。上游说明这些示例模型依照 [Live2D Free Material License](https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html) 重新分发，模型素材不随本项目代码许可证重新授权。
- 在 `apps/web` 运行 `npm test` 会检查配置引用的所有资源及模型/贴图文件签名。

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
cd apps/web/public/live2d
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
