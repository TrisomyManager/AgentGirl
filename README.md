# AgentGril — 小暖 Companion AI（monorepo）

单仓库三端分区：**后端**、**Web 前端**、**PC 设备模拟客户端**，并附带 **`packages/contracts`** 契约草案与 **`integration`** 联调脚本。不引入 AIRI / Hermes / OpenTalking 等完整外部工程源码。

## 目录结构

| 路径 | 说明 |
|------|------|
| [`apps/backend/`](apps/backend/) | FastAPI 单体与 Python 模块（原 `companion-ai` 主树） |
| [`apps/web/`](apps/web/) | Vue 3 + Vite 调试/预览 UI |
| [`apps/pc-client/`](apps/pc-client/) | Device Operation Gateway 的 HTTP 轮询模拟客户端 |
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

**PC 模拟客户端**：

```bash
cd apps/pc-client
pip install httpx
# 可选: pip install -e .
python sim_client.py
# 或
python -m xiaonuan_pc_client
```

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

- **Device Gateway** 是后端能力（`device_coordination`）；PC 客户端仅作为设备执行端模拟，不含远控或常驻 Windows 客户端实现。
