# shared_runtime

> 宿主可注入的运行时层 · LLM 客户端 / 配置 / Lite Mode / 数据库生命周期。

## 我是什么

`shared_runtime` 是 V2 重构波次 2 落地的**运行时层**包，承载所有"有副作用"的运行时组件：

- 配置加载（`Settings` / `get_settings`）
- LLM 客户端默认实现（`LLMClient`，已实现 `LLMClient` Protocol 形状）
- LLM / 语音运行时配置热更新
- Lite Mode 判断（`is_lite_mode()`）
- 数据库生命周期（`init_database_schema` / `close_database`）

第三方宿主可以**整体替换本包**——把自家 LLM 客户端、自家配置、自家数据库换上去。

> 当前是 re-export shim（透传 `shared.config` / `shared.llm_client` / `shared.voice_runtime_config` / `shared.database`）；V2.1 起物理迁入。

## 暴露什么 API

```python
from shared_runtime import (
    Settings, get_settings,
    LLMClient, chunk_text_stream,
    get_runtime_llm_config, update_runtime_llm_config,
    get_runtime_voice_config, update_runtime_voice_config,
    init_database_schema, close_database,
    is_lite_mode,
)
```

## 依赖什么

- companion-ai 内部：`shared_contracts`（隐式，作为 LLMClient Protocol 的来源）
- 第三方：`pydantic-settings` / `httpx` / `sqlalchemy[asyncio]` / `aiosqlite`（Lite）/ `asyncpg`（PG）

## 怎么单独启

```bash
cd companion-ai
COMPANION_LITE_MODE=true python -m shared_runtime
# 打印当前 settings、lite_mode、LLM provider、数据库 URL
```

## 最小用法

```python
import os, asyncio
os.environ["COMPANION_LITE_MODE"] = "true"

from shared_runtime import get_settings, is_lite_mode, LLMClient

settings = get_settings()
print(settings.app_name, is_lite_mode())

async def chat():
    client = LLMClient()
    reply = await client.chat([{"role": "user", "content": "你好"}])
    print(reply)

# asyncio.run(chat())  # 需要配置 OPENAI_API_KEY 之类的密钥
```

## 第三方宿主接入提示

如果宿主已经有自家 LLM 客户端：实现 `LLMClient` Protocol（来自 `shared_contracts`）的 `.chat()` / `.stream()` 即可注入到任意上游业务模块（`persona_engine` / `memory_system` 等都只依赖 Protocol 形状）。
