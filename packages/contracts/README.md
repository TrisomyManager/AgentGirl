# 小暖跨端契约（contracts）

本目录是 **协议与 schema 的聚合点**，不是业务实现。后端（`apps/backend`）中的 FastAPI / Pydantic 模型仍是**权威实现**；此处存放供 Web、PC 模拟客户端与外部集成参考的 **OpenAPI 占位说明** 与 **JSON Schema 草案**。

## 依赖边界

- **前端**（`apps/web`）与 **PC 模拟客户端**（`apps/pc-client`）应只依赖本包中的公开契约（或由此生成的类型），**不得** `import` 后端 Python 业务模块。
- **后端**修改 Device Gateway 等对外行为时，必须同步更新 `schemas/` 草案与 [`API_CHANGELOG.md`](API_CHANGELOG.md)。

## 目录

| 路径 | 说明 |
|------|------|
| `openapi/` | OpenAPI 导出说明（完整 spec 可由后端生成后拷贝至此） |
| `schemas/` | JSON Schema 草案（Device Gateway 等） |
| `typescript/` | 未来：由 schema 生成的 TS 类型入口 |
| `python/` | 未来：由 schema 生成的 Python 类型入口（非后端业务包） |

## 联调排障字段

跨端查问题时，在日志与请求中尽量对齐以下字段（见 [`integration/README.md`](../../integration/README.md)）：

| 字段 | 用途 |
|------|------|
| `x-request-id` | 单次 HTTP 请求关联（网关、反向代理、客户端可透传） |
| `user_id` | 用户维度 |
| `session_id` | 会话 / 对话维度 |
| `device_id` | 设备实例 |
| `command_id` | 设备指令单号 |
| `audit_id` | 审计行 ID（若后端返回） |

**说明**：本轮以文档约定为主；不要求所有路由已实现 `x-request-id` 中间件，但联调脚本会生成并打印示例 ID。
