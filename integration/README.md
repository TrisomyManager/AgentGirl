# 联调（integration）

本目录提供 **Windows PowerShell** 下的轻量启动脚本与 **Device Gateway 冒烟** 脚本。不要求 Docker；默认假设后端为 Lite Mode（`COMPANION_LITE_MODE=true`）。

## 排障字段（统一约定）

联调时在日志、抓包、后端日志中尽量对齐以下 ID，便于串起一次完整设备指令流：

| 字段 | 说明 |
|------|------|
| `x-request-id` | 单次 HTTP 请求；脚本会生成 GUID 并打印 |
| `user_id` | 用户 |
| `session_id` | 对话会话（聊天/语音链路） |
| `device_id` | 设备 |
| `command_id` | 设备指令 |
| `audit_id` | 审计记录（若响应体含 `audit_id`） |

## 故障归属（快速判断）

| 现象 | 优先怀疑 |
|------|----------|
| `GET /health` 不通 | **backend** 未启动或端口错 |
| 浏览器页面打不开，但 `curl` API 正常 | **web**（Vite、端口、`VITE_API_BASE_URL`） |
| 设备列表始终离线 | **pc-client** 未跑、或 register/heartbeat 失败 |
| 指令已创建（API 返回 success）但长期未被领取 | **pc-client** 未轮询 `claim_next` 或 transport 配置 |
| `command_result` 4xx/5xx | **pc-client** `device_token` 过期/错误，或 **backend** 校验失败 |
| 后端显示成功但 UI 不刷新 | **web** 轮询/状态同步 |

## 脚本

| 脚本 | 作用 |
|------|------|
| [`scripts/start-backend.ps1`](scripts/start-backend.ps1) | 进入 `apps/backend` 启动 uvicorn |
| [`scripts/start-web.ps1`](scripts/start-web.ps1) | 进入 `apps/web` 启动 Vite |
| [`scripts/start-pc-sim.ps1`](scripts/start-pc-sim.ps1) | 进入 `apps/pc-client` 启动模拟客户端 |
| [`scripts/smoke-device-flow.ps1`](scripts/smoke-device-flow.ps1) | 对运行中的后端跑设备网关冒烟（需 httpx 仅后端；脚本用 `Invoke-RestMethod`） |

## 典型顺序

1. 终端 A：`.\integration\scripts\start-backend.ps1`
2. 终端 B：`.\integration\scripts\start-web.ps1`（可选）
3. 终端 C：`.\integration\scripts\start-pc-sim.ps1`（可选，与冒烟二选一验证）
4. 冒烟：`cd integration` → `.\scripts\smoke-device-flow.ps1`（默认 `http://127.0.0.1:8000`；若 8000 被占用，后端可起在 8010，并执行 `.\scripts\smoke-device-flow.ps1 -BaseUrl http://127.0.0.1:8010`）

## 端到端测试

见 [`tests/README.md`](tests/README.md)（占位；后续可加 Playwright/pytest 跨端用例）。
