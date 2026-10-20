# persona_engine

> 角色引擎 · YAML 定义的人格 + 情绪状态机 + 关系追踪 + 语气生成。

## 我是什么

`persona_engine` 把"小暖"等陪伴角色的**人格定义、情绪、关系**抽离为可独立部署的能力包：

- **人格仓库**（`persona_store`）：从 `data/personas/<role_id>.yaml` 加载 `PersonaProfile`，波次 4 起支持多角色
- **连续情绪**（`EmotionEngine`）：valence ∈ [-1, 1]、arousal ∈ [0, 1]，有界过渡和确定性时间平复；11 种标签用于兼容呈现
- **关系追踪**（`RelationshipTracker`）：intimacy / trust / familiarity / affection 四维度持久化
- **独立反应**（`ReactionClassifier` / `ReactionService`）：生成前分析用户输入，完成后按 turn_id 原子提交情绪与关系；模型错误/超时回退到规则
- **日关系复核**（`RelationshipReviewer`）：宿主提供原始轮次，补偿新版档案的漏记事务；不重复给旧档案计分，不修改当前情绪或今日活跃时间
- **语气生成**（`ToneGenerator`）：根据情绪 + 关系生成 system prompt 中的语气片段

## 暴露什么 API

顶层包仅暴露 `__version__`；常用子模块速查：

```python
from persona_engine.persona_store import (
    get_persona_profile, get_persona_profile_async,
    load_persona, load_persona_by_role,
    list_available_personas, PersonaStoreError,
)
from persona_engine.emotion_engine import EmotionEngine
from persona_engine.relationship_tracker import RelationshipTracker
from persona_engine.tone_generator import ToneGenerator
from persona_engine.api import router         # FastAPI router
from persona_engine.main import app           # 独立 FastAPI app（端口 8001）
```

## 依赖什么

- companion-ai 内部：`shared_contracts`（PersonaProfile / EmotionState / EmotionTag / RelationshipMetrics）、`shared_runtime`（LLMClient）
- 第三方：`pyyaml` / `structlog` / `fastapi` / `pydantic` / `uvicorn` / `sqlalchemy[asyncio]`

## 怎么单独启

```bash
# 方式 1：独立 FastAPI 微服务
cd apps/backend
COMPANION_LITE_MODE=true python -m persona_engine
# → http://localhost:8001/docs

# 方式 2：在你自己的代码里 import 用
```

## 最小用法

```python
from datetime import datetime
from persona_engine.persona_store import get_persona_profile, list_available_personas
from persona_engine.tone_generator import ToneGenerator
from shared_contracts import EmotionState, EmotionTag, RelationshipMetrics

print(list_available_personas())   # ['aria', 'default', 'xiaonuan']

profile = get_persona_profile(role_id="default")  # 默认是「小暖」
tone = ToneGenerator(profile)

emo = EmotionState(
    primary=EmotionTag.HAPPY, intensity=0.6,
    valence=0.4, arousal=0.5,
    trigger="user_msg", timestamp=datetime.utcnow(),
)
rel = RelationshipMetrics(user_id="u1")
print(tone.generate_tone(emo, rel))
```

## 第三方宿主接入提示

宿主只需提供：
1. `data/personas/<your_role>.yaml`（参考 `data/personas/default.yaml`）
2. 一个实现 `LLMClient` Protocol 的客户端（用于语气微调）

即可在自家工程独立运行 persona_engine，无需引入 `core_orchestrator`。

## 持久化与验证（V2.8）

参考应用在 Lite 与 PostgreSQL 模式下都使用 `PersonaStateStore` 保存情绪和关系；SQL 是权威数据源，Redis 可用性不会改变状态。直接构造 `EmotionEngine()` / `RelationshipTracker()` 仍可供临时原型使用；需要跨重启保留时注入同一个 `PersonaStateStore(session_factory)`。

`ReactionService.predict()` 是不写入的生成前预览。`commit(user_id, turn_id, message, reaction)` 在一个事务内重新计算并保存情绪/关系；同一用户/轮次重放只返回已提交结果。用户表达负面情绪不会降低信任，明确的敌意信号才会触发有限调整。

- `POST /persona/classify_reaction`：仅分类，无状态写入。
- `POST /persona/generate_response`：可传 `turn_id` 和宿主已分类的 `reaction`。
- `GET /persona/relationship_reviews/{user_id}`：查看按日的观察统计。
- `COMPANION_REACTION_MODEL` 可覆盖为独立小模型，空值沿用默认模型；`COMPANION_REACTION_TIMEOUT_SECONDS` 默认为 3 秒，`COMPANION_REACTION_USE_LLM=false` 强制离线规则。
- `shared_runtime.response_behavior` 为普通与流式回复共用 temperature、token 预算和语气/emoji 约束；任务需要的细节优先。

验证：`pytest -q persona_engine/tests core_orchestrator/tests/test_runtime_hooks.py memory_system/tests/test_dream.py`。真实方舟分类、SQL 重启与 Dream 复核去重已在隔离数据中验证；生产 PostgreSQL、实时语音独立分类与完整用户数据清除继续作为未完成工作。

## 自然发言（V2.9）

`ConversationPreferencesStore` 按用户保存自然发言开关与简短回应的回复概率，默认关闭。`reply_policy.decide_reply()` 接收宿主的最新上下文，只有独立的简短回应才使用概率选择；确认、任务、语音/图片和低落上下文受保护，不会连续两次安静处理。缺失上下文时正常回复。

参考宿主通过 `GET/PUT /persona/conversation_preferences/{user_id}` 配置。`reply_suppressed=true` 是成功处理的接收状态，宿主仍需保存原文与调用 `ReactionService.commit()`，不生成空白助手消息或音频。独立服务可使用 `POST /persona/observe_turn` 提交同一用户/turn_id 的观察。运行测试：`pytest -q persona_engine/tests/test_reply_policy.py core_orchestrator/tests/test_natural_reply.py`。
