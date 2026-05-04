# Live2D 集成测试指南

## ✅ 已完成的工作

### 1. 依赖安装
```bash
npm install pixi.js@7.x pixi-live2d-display@0.4.0
```

### 2. 核心文件创建

- **[useLive2D.ts](../frontend_app/src/composables/useLive2D.ts)** - Live2D可组合函数
  - 封装PixiJS应用初始化
  - 模型加载与缩放适配
  - 动作播放、表情切换API
  - 自动清理资源

- **[AvatarDisplay.vue](../frontend_app/src/components/AvatarDisplay.vue)** - 改造完成
  - 集成Live2D画布
  - 加载状态占位符
  - 错误降级到静态图片
  - 情绪→动作映射逻辑
  - 打字状态→动作联动

### 3. 测试模型配置

使用免费CDN模型进行技术验证：
```typescript
modelPath: 'https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/shizuku/shizuku.model.json'
```

## 🧪 测试步骤

### 1. 启动服务

```bash
# 后端（如果未启动）
cd companion-ai
COMPANION_LITE_MODE=true uvicorn core_orchestrator.main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd frontend_app
npm run dev
```

### 2. 访问页面

打开浏览器：http://localhost:5173

### 3. 验证功能

#### ✅ 基础加载
- [ ] 页面加载时显示"加载小暖中..."spinner
- [ ] 2-5秒后Live2D模型出现（蓝发少女"しずく"）
- [ ] 模型居中显示，尺寸适配容器

#### ✅ 鼠标交互
- [ ] 鼠标悬停在模型上，角色眼睛跟随鼠标移动
- [ ] 点击模型不同区域触发不同动作：
  - 点击头部 → 摇头
  - 点击身体 → 挥手/其他动作
  - 点击手臂 → 特殊动作

#### ✅ 情绪联动
在浏览器控制台测试（F12）：

```javascript
// 模拟发送消息，触发情绪变化
// 在Chat界面输入消息，观察：
// - happy → tap_body动作
// - sad → flick_head动作
// - excited → shake动作
```

#### ✅ 打字状态
- [ ] AI回复时（isTyping=true），模型播放tap_body动作

#### ✅ 错误降级
强制触发错误测试：

```typescript
// 修改modelPath为无效URL
modelPath: 'https://invalid.url/model.json'
// 预期：显示静态占位图片，无白屏崩溃
```

### 4. 控制台检查

打开浏览器控制台（F12），预期输出：

```
Live2D model loaded successfully
Available Live2D motion groups: ["idle", "tap_body", "shake", "flick_head", "pinch_in", ...]
```

## 🐛 常见问题排查

### 问题1: 白屏/模型不显示

**可能原因：**
- CORS跨域问题（CDN模型被浏览器拦截）
- 网络超时

**解决方案：**
```bash
# 检查浏览器控制台Network标签
# 如果看到CORS错误，说明CDN不可用
# 解决方法：下载模型到本地

cd frontend_app/public/live2d
# 手动下载shizuku模型文件
# 修改modelPath为: '/live2d/shizuku/shizuku.model.json'
```

### 问题2: 模型加载但无动作

**检查：**
```javascript
// 控制台执行
console.log(getMotionGroups())
// 如果返回空数组，说明模型缺少motions定义
```

**解决方案：**
- Shizuku模型确实包含动作定义
- 检查网络请求是否完整加载了`.mtn`动作文件

### 问题3: TypeScript类型错误

```bash
# 如果IDE报类型错误
npm install --save-dev @types/pixi.js
```

### 问题4: 性能卡顿

**检查设备性能：**
```javascript
console.log(navigator.hardwareConcurrency) // CPU核心数
// 如果 < 4，考虑禁用Live2D，回退到静态图片
```

## 📊 技术验证清单

| 验证项 | 状态 | 备注 |
|--------|------|------|
| PixiJS正确初始化 | ⏳ 待测试 | 检查canvas元素生成 |
| Live2D模型加载 | ⏳ 待测试 | 检查网络请求200 |
| 鼠标交互响应 | ⏳ 待测试 | 眼球跟随 + 点击动作 |
| 情绪→动作映射 | ⏳ 待测试 | happy触发tap_body |
| 打字状态联动 | ⏳ 待测试 | isTyping触发动画 |
| 错误降级机制 | ⏳ 待测试 | 加载失败显示静态图 |
| 资源清理 | ⏳ 待测试 | 组件卸载无内存泄漏 |

## 🎯 下一步计划

### 短期（验证成功后）
1. ✅ 技术栈验证通过
2. 记录实际性能指标（首次加载时间、FPS、内存占用）
3. 整理对"小暖"专属模型的需求规格

### 中期（2周内）
1. 制定Live2D模型委托需求文档
2. 寻找外包设计师（站酷/猪八戒网）
3. 设计"小暖"角色设定（发型、服装、配色）

### 长期（4周内）
1. 获得"小暖"专属`.moc3`模型
2. 定义8-12组动作（idle/happy/sad/thinking/typing/greeting/waving/surprised）
3. 定义5-8种表情切换
4. 优化资源加载（WebP压缩、懒加载）
5. 实现高级交互（说话时口型同步）

## 🔗 相关资源

- [Live2D官方文档](https://docs.live2d.com/)
- [pixi-live2d-display GitHub](https://github.com/guansss/pixi-live2d-display)
- [免费样本模型下载](https://www.live2d.com/en/download/sample-data/)
- [Cubism Editor（模型制作工具）](https://www.live2d.com/en/download/cubism/)

## 📝 测试报告模板

测试完成后，请填写：

```
测试日期：____
浏览器：Chrome / Firefox / Safari
设备：Windows / macOS / Linux

【基础功能】
- 模型加载：✅ / ❌ （耗时：___秒）
- 鼠标交互：✅ / ❌
- 动作播放：✅ / ❌
- 错误降级：✅ / ❌

【性能指标】
- 首次加载时间：___秒
- 模型文件大小：___MB
- 运行时FPS：___
- 内存占用：___MB

【问题记录】
1. ...
2. ...

【建议】
1. ...
2. ...
```
