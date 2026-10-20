# memory_system

> 长期记忆系统 · 5 阶段管线 + 向量召回 + 知识图谱 + Working Memory。

## 我是什么

`memory_system` 是陪伴 AI 的**长短期记忆**统一接入层：

- **5 阶段管线**：Raw → Entity → Importance → Conflict → Long-term
- **向量存储**：PostgreSQL + pgvector（Lite Mode 自动降级到 SQLite）
- **关系检索**：按用户隔离的 SQL 实体/关系索引 + 个性化 PageRank，与向量排序融合；Neo4j 是可选外部适配。
- **对话存档**：SQLite / PostgreSQL 持久化；Redis 维护临时用户上下文。
- **Working Memory**：滚动 N 轮、窗口外摘要与结构事实；配置密钥后默认按批次压缩旧对话，可选额外精炼窗口主题。
- **可恢复遗忘**：基于重要性、时间和访问频率计算清晰度；淡化后保留原文，明确检索和手动恢复可重新激活。
- **离线整理**：当地凌晨 2–6 点、至少 30 分钟无用户互动时生成日总结，默认追赶最近 7 天；按指纹和数据库租约避免重复调用。

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
cd apps/backend
COMPANION_LITE_MODE=true python -m memory_system
# → http://localhost:8002/docs

# 方式 2：在自己的脚本里 import 用（见下方最小用法）
```

## 最小用法（Lite Mode，无 Docker）

```python
import asyncio, os
os.environ["COMPANION_LITE_MODE"] = "true"

from memory_system.db import AsyncSessionLocal, init_schema
from memory_system.vector_store import store_memory
from memory_system.recall import recall_memory
from shared_contracts.models import MemoryCategory, MemoryEntry

async def demo():
    await init_schema()
    async with AsyncSessionLocal() as session:
        entry = await store_memory(session, MemoryEntry(
            entry_id="", user_id="u1", category=MemoryCategory.FACT,
            content="用户养了宠物猫 Mimi", importance=0.7,
        ))
        hits = await recall_memory(session, user_id="u1", query="Mimi", top_k=3)
        print(entry.entry_id, [memory.content for memory in hits.entries])

asyncio.run(demo())
```

> 向量默认使用豆包多模态文本向量。未配置 Key 时，本地词项与关系索引仍可检索；哈希向量用于一致性匹配。生成式摘要失败时保留明确标注的摘录。

## 维护与回顾 API

- `POST /memory/maintenance/decay`：按访问与时间淡化，原文保留。
- `POST /memory/user/{user_id}/restore/{memory_id}`：恢复该用户的一条记忆。
- `POST /memory/user/{user_id}/consolidate`：整理今天，或传 `{"day":"2026-10-19"}` 指定日期。
- `GET /memory/user/{user_id}/daily_summaries`：读取日总结与明确的偏好变化。
- `DELETE /memory/user/{user_id}/all`：原子清除记忆库、相关索引、对话存档与回顾；后台旧写入失效。

数据库使用 WAL 支持 Lite 读写并发。对话原文以 SQL 为主存，旧 Redis 临时对话缓存不再作为恢复来源，避免已删除内容重新出现。`delete_expired` 是保留的旧显式工具；默认维护调度不调用它。

配置：`COMPANION_ENABLE_LOCAL_MEMORY_GRAPH`、`COMPANION_WORKING_MEMORY_COMPRESSION_USE_LLM`、`COMPANION_WORKING_MEMORY_COMPRESSION_BATCH_TURNS`、`COMPANION_MEMORY_MAINTENANCE_ENABLED`、`COMPANION_MEMORY_MAINTENANCE_INTERVAL_SECONDS`、`COMPANION_MEMORY_DREAM_USE_LLM`、`COMPANION_MEMORY_DREAM_BACKFILL_DAYS`、`COMPANION_MEMORY_TIMEZONE`。参考应用使用用户主动陪伴设置中的时区。

## 当前验收边界

Lite 本地关系检索、恢复、日总结、跨会话回顾与真实方舟摘要已验证。PostgreSQL/Neo4j 实例联调及关系指标的离线复核仍按执行清单继续推进。

## 第三方宿主接入提示

宿主可以只取 `vector_store` + `working` 两个子模块，把 5 阶段管线（依赖 Celery）跳过，直接基于 `LLMClient` Protocol 注入自家 embedding 服务。
