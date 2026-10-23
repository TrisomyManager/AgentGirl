# AgentGril — 小暖 Companion AI（monorepo）

单仓库三端分区：**后端**、**Web 前端**、**Electron PC 客户端**，并附带 **`packages/contracts`** 契约草案与 **`integration`** 联调脚本。不引入 AIRI / Hermes / OpenTalking 等完整外部工程源码。

## 目录结构

| 路径 | 说明 |
|------|------|
| [`apps/backend/`](apps/backend/) | FastAPI 单体与 Python 模块（原 `companion-ai` 主树） |
| [`apps/web/`](apps/web/) | Vue 3 + Vite 调试/预览 UI |
| [`apps/pc-client/`](apps/pc-client/) | Electron/Vue 桌面端、设备桥与可选透明桌宠 |
| [`packages/contracts/`](packages/contracts/) | 跨端协议草案（JSON Schema 等） |
| [`integration/`](integration/) | PowerShell 启动与冒烟脚本 |
| [`companion-ai/README.md`](companion-ai/README.md) | 兼容入口：指向新路径 |

## 各端启动

**后端**（仓库根目录下）：

```bash
cd apps/backend
# Windows PowerShell: $env:COMPANION_LITE_MODE="true"
COMPANION_LITE_MODE=true uvicorn main:app --reload --port 8000
```

**Web**：

```bash
cd apps/web
npm install
# PowerShell
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
npm run build
```

**PC 客户端**（Windows，Node 22.23 / 24.19 验证构建）：

```powershell
cd apps/pc-client
npm ci
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
$env:XIAONUAN_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```

在设置中的“陪伴与功能”启用桌宠并导入 WebM/GIF 角色目录。桌面情境陪伴默认关闭，开启需要全局模块与当前用户双重授权；详见 [dsh-pet 对比、接入与验收](apps/backend/docs/dsh-pet-adoption.md)。原 Python 设备模拟器位于 `apps/pc-client/legacy_python/`，仍可用于设备网关联调。

环境变量（可选）：`XIAONUAN_API_BASE_URL`、`XIAONUAN_USER_ID`、`XIAONUAN_DEVICE_ID`、`XIAONUAN_DEVICE_NAME`。

## 联调

见 [`integration/README.md`](integration/README.md)。冒烟（需后端已启动）：

```powershell
cd integration
.\scripts\smoke-device-flow.ps1
```

## 开发与测试入口

详见 [`AGENTS.md`](AGENTS.md) 与 [`.cursor/skills/cloud-agents/SKILL.md`](.cursor/skills/cloud-agents/SKILL.md)。**Agent / 自动化请从 `apps/backend`、`apps/web`、`apps/pc-client` 起跳**；勿使用已废弃的 `companion-ai/frontend_app` 或 `companion-ai/examples/device_client`（`companion-ai/README.md` 仅为书签）。

## 概念边界

- **Device Gateway** 是后端能力（`device_coordination`）；Electron PC 客户端承载已有设备桥和展示层；主动关怀的决策、人格与记忆仍由后端负责。
