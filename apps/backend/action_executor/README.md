# 本地插件（V2.15）

目录发现、宿主授权、热重载及资源生命周期见 [plugins/README.md](../plugins/README.md)。默认只发现，不运行代码；插件工具与内置/MCP 工具共用 `ToolCatalog` 和任务接口。宿主授权及命令配置不由聊天修改。

﻿# action_executor

> 能力执行器 · 时间 / 天气 / 提醒 + 主动推送总线 + 后台调度。

## 我是什么

`action_executor` 承载"陪伴 AI 能真正帮用户做的事"，与负责 2D 动画的 `action_layer`（已 deprecated）不同：

- **可插拔注册表**（`ActionRegistry` + `@register_action`）
- **13 个内置 handler**：时间、天气、提醒、记忆、资料、搜索与设备工具。
- **提醒持久化**：`RemindersStore`（SQLite/PG），支持相对延迟 + 固定间隔重复（"每 N 分钟/小时/天"）
- **后台调度器**：`ReminderScheduler` 轮询触发，自动顺延 `fire_at`
- **主动推送总线**：`ProactivePushBus` 进程内 pub/sub → SSE/poll 推到前端

## 暴露什么 API

```python
from action_executor import (
    # 注册表
    ActionRegistry, ActionResult, register_action, get_registry,
    # 内置
    BUILTIN_ACTIONS, ensure_builtins_registered,
    # 提醒
    Reminder, ReminderScheduler, RemindersStore, get_reminders_store,
    # 推送
    ProactivePushBus, get_proactive_push_bus,
)
from action_executor.api import router       # FastAPI /actions
from action_executor.main import app         # 独立 app（端口 8007）
```

## 依赖什么

- companion-ai 内部：`shared_runtime`（数据库生命周期）
- 第三方：`httpx`（Open-Meteo）/ `sqlalchemy[asyncio]` / `structlog` / `fastapi` / `uvicorn`

## 怎么单独启

```bash
# 方式 1：独立 FastAPI 微服务
cd apps/backend
COMPANION_LITE_MODE=true python -m action_executor
# → http://localhost:8007/docs

# 方式 2：在自己的脚本里 import 用
```

## 最小用法

```python
import asyncio
from action_executor import ensure_builtins_registered, get_registry

ensure_builtins_registered()
registry = get_registry()

async def demo():
    res = await registry.dispatch_contextual("get_time", {}, user_id="local-user")
    print(res.ok, res.message, res.data)

    weather = await registry.dispatch_contextual("get_weather", {"location": "Beijing"}, user_id="local-user")
    print(weather.ok, weather.message)

asyncio.run(demo())
```

## 注册自定义 Action

```python
from action_executor import register_action, ActionResult

@register_action(
    name="say_hello",
    description="Greet the user by name.",
    params_schema={"type": "object", "properties": {"name": {"type": "string"}}},
)
async def say_hello(params):
    return ActionResult(ok=True, message=f"hi {params.get('name', 'friend')}")
```

## 第三方宿主接入提示

宿主不需要主链路就能跑：直接 `ensure_builtins_registered()` + `registry.dispatch_contextual(...)` 即可；后台 reminder scheduler 通过 `ReminderScheduler.start()` 启用。

## V2.10 · MCP 与多步任务

`registry.mcp_tools()` / `GET /actions/mcp/tools` 输出真正的 JSON Schema。`dispatch_contextual` 校验有限 JSON、参数类型、范围、日期和额外字段，再绑定宿主的 user/session/turn/operation 标识。模型不能填写或覆盖这些标识。原有 `dispatch` 保留给可信内部调用。

内置工具的 stdio MCP 服务使用官方 SDK，可由宿主固定用户启动：

```powershell
python mcp_actions_server.py --user-id local-user --session-id mcp-session
```

stdout 仅传输协议，日志写 stderr。外部服务器支持 stdio 和 Streamable HTTP，通过 `COMPANION_MCP_CONFIG_FILE` 指向本地配置；文件格式示例：

```json
{"servers":[{"name":"reference","transport":"streamable_http","url":"http://127.0.0.1:9000/mcp","allowed_users":["local-user"],"allow_mutations":false}]}
```

stdio 配置使用 `command`、`args`、可选 `env`；HTTP 支持 `headers`。认证信息仅保存在忽略的 `companion_mcp_config.json`，不提交密钥或认证头。服务器可用用户由宿主配置，不能由聊天输入创建连接。绑定单个用户凭据的服务器应只列出该用户。工具以 `服务器名__工具名` 命名，未标记只读的外部工具默认不启用；模型看不到身份参数，服务声明需要时由宿主绑定。这些限制不代替后续插件授权和设备沙箱。

`TaskAgent` 可独立接入，通过 `ToolCatalog` / `ToolContext` 和可注入的 planner 使用本地或外部工具。默认最多 6 个工具步骤、60 秒总时限、12 秒规划时限和 15 秒单步时限。仅保存简短动作说明和实际工具结果，不保存模型推理。失败即停止；同一轮重发返回原执行记录，相同工具/参数不重做；未知结果与进程重启不会自动重放。

接口：`POST /actions/tasks` 接收 `user_id/session_id/request` 和可选 `turn_id`；`GET /actions/tasks?user_id=...` 与 `GET /actions/tasks/{id}?user_id=...` 查询；`DELETE /actions/tasks/{id}?user_id=...` 停止；`POST /actions/tasks/{id}/resume` 接收 `user_id/clarification`。只有 `awaiting_input` 可继续，已完成步骤保留。其他用户查询或操作返回 404。生产部署仍需宿主认证绑定，当前接口沿用项目的 user_id 契约。

SQLite/PG 共享 `task_runs/task_steps` 表；单进程宿主启动时把遗留 running 标记 interrupted，把执行中的步骤标记 outcome_unknown。不可把多个独立 worker 同时挂到这一恢复流程；分布式租约仍需另行实现。

```powershell
pytest -q action_executor/tests/test_tool_protocol.py action_executor/tests/test_task_agent.py action_executor/tests/test_task_api.py
```

协议回归会启动真实的官方 MCP stdio/HTTP 测试服务器与本地动作桥，不需要外部凭据。
