# action_executor

> 能力执行器 · 时间 / 天气 / 提醒 + 主动推送总线 + 后台调度。

## 我是什么

`action_executor` 承载"陪伴 AI 能真正帮用户做的事"，与负责 2D 动画的 `action_layer`（已 deprecated）不同：

- **可插拔注册表**（`ActionRegistry` + `@register_action`）
- **5 个内置 handler**：`get_time` / `get_weather`（Open-Meteo，无需 API key）/ `set_reminder` / `list_reminders` / `cancel_reminder`
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
cd companion-ai
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
    res = await registry.invoke("get_time", {"timezone": "Asia/Shanghai"})
    print(res.ok, res.message, res.data)

    weather = await registry.invoke("get_weather", {"city": "Beijing"})
    print(weather.ok, weather.message)

asyncio.run(demo())
```

## 注册自定义 Action

```python
from action_executor import register_action, ActionResult

@register_action(
    name="say_hello",
    description="Greet the user by name.",
    schema={"type": "object", "properties": {"name": {"type": "string"}}},
)
async def say_hello(params):
    return ActionResult(ok=True, message=f"hi {params.get('name', 'friend')}")
```

## 第三方宿主接入提示

宿主不需要主链路就能跑：直接 `ensure_builtins_registered()` + `registry.invoke(...)` 即可；后台 reminder scheduler 通过 `ReminderScheduler.start()` 启用。
