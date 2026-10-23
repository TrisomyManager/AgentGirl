# API 变更日志（contracts）

记录影响 **Web / PC 模拟客户端 / 外部集成** 的协议变更。格式建议沿用 [Keep a Changelog](https://keepachangelog.com/)。

## [Unreleased]

### Added

- `GET/PUT /settings/features`：全局可选功能的本次启用/待启用列表及依赖；保存整值、重启生效；非法 ID/依赖 422、写盘失败 503。
- `GET/PUT /actions/proactive/preferences?user_id=…`：用户级主动关怀与桌面情境授权、进程白名单、停留/闲置阈值。
- `POST /actions/proactive/context`：进程名/闲置/忙碌元数据，返回门禁结果；需功能与用户双重启用，额外字段 422。无截图或窗口标题字段。
- `proactive_message.trigger_type` 增加 `desktop_context`；既有事件形状保持不变。Web 按用户与消息 ID 对 SSE/轮询去重。
- 详见 [接入说明与请求字段](../../apps/backend/docs/dsh-pet-adoption.md)。

### 文档

- 初始化 monorepo `packages/contracts` 骨架与 Device Gateway JSON Schema 草案（与当前后端行为对齐，非代码生成）。

## 维护约定

- **PATCH**：字段可选化、文档澄清、新增仅可选字段 —— 更新本文件 **Added**。
- **MINOR**：新增端点、响应新增字段（旧客户端可忽略）— **Added**。
- **MAJOR**：删除字段、改 URL、改认证方式 —— **Breaking**，并同步 `COMPATIBILITY.md`。
