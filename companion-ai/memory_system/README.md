# memory_system

> 长期记忆系统 · 5 阶段管线 + 向量召回 + 知识图谱 + Working Memory。

## 我是什么

`memory_system` 是陪伴 AI 的**长短期记忆**统一接入层：

- **5 阶段管线**：Raw → Entity → Importance → Conflict → Long-term
- **向量存储**：PostgreSQL + pgvector（Lite Mode 自动降级到 SQLite）
- **知识图谱**：Neo4j（Lite Mode 跳过）
- **短时缓存**：Redis（Lite Mode 内存兜底）
- **Working Memory**：滚动 N 轮 + 结构化用户摘要 + 可选 LLM 一次 JSON 精炼（topic + digest）

## 暴露什么 API

顶层包仅暴露 `__version__`；常用子模块速查：

```python
from memory_system.db import (
    get_db, AsyncSessionLocal, init_schema, close_engine,
)
from memory_system.vector_store import (
    store_memory, search_similar, delete_expired,
    decay_low_importance, list_user_memories,
    delete_user_memories, delete_memory_by_id,
    get_user_memory_summary, resolve_embedding_dim,
)
from memory_system.recall import recall_memory
from memory_system.pipeline import run_memory_pipeline      # Celery
from memory_system.working import get_working_memory
from memory_system.short_term import short_term_memory, close_redis
from memory_system.graph_store import graph_store
from memory_system.api import router          # FastAPI /memory
from memory_system.main import app            # 独立 app（端口 8002）
```

## 依赖什么

- companion-ai 内部：`shared_contracts`（MemoryEntry / MemoryRecallResult）、`shared_runtime`（数据库生命周期、LLMClient）
- 第三方：`sqlalchemy[asyncio]` / `asyncpg` / `aiosqlite` / `pgvector`（PG 模式）/ `neo4j`（PG 模式）/ `redis` / `celery` / `httpx`

## 怎么单独启

```bash
# 方式 1：独立 FastAPI 微服务
cd companion-ai
COMPANION_LITE_MODE=true python -m memory_system
# → http://localhost:8002/docs

# 方式 2：在自己的脚本里 import 用（见下方最小用法）
```

## 最小用法（Lite Mode，无 Docker）

```python
import asyncio, os
os.environ["COMPANION_LITE_MODE"] = "true"

from memory_system.db import AsyncSessionLocal, init_schema
from memory_system.vector_store import store_memory, search_similar
from shared.models import MemoryCategory

async def demo():
    await init_schema()
    async with AsyncSessionLocal() as session:
        mem_id = await store_memory(
            session, user_id="u1", category=MemoryCategory.FACT,
            content="用户养了一只叫 Mimi 的猫", importance=0.7,
        )
        hits = await search_similar(session, query="宠物", user_id="u1", top_k=3)
        print(mem_id, [h.content for h in hits])

asyncio.run(demo())
```

> **注意**：`store_memory` / `search_similar` 需要 embeddings；Lite Mode 默认会用 LLMClient 默认实现，因此需要配置 `OPENAI_API_KEY` 或兼容 endpoint，或在测试中 monkey-patch embeddings 方法。

## 第三方宿主接入提示

宿主可以只取 `vector_store` + `working` 两个子模块，把 5 阶段管线（依赖 Celery）跳过，直接基于 `LLMClient` Protocol 注入自家 embedding 服务。
