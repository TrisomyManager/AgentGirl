# persona_engine

> 角色引擎 · YAML 定义的人格 + 情绪状态机 + 关系追踪 + 语气生成。

## 我是什么

`persona_engine` 把"小暖"等陪伴角色的**人格定义、情绪、关系**抽离为可独立部署的能力包：

- **人格仓库**（`persona_store`）：从 `data/personas/<role_id>.yaml` 加载 `PersonaProfile`，波次 4 起支持多角色
- **情绪状态机**（`EmotionEngine`）：7 种基础情绪 + 时间衰减
- **关系追踪**（`RelationshipTracker`）：intimacy / trust / familiarity / affection 四维度持久化
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
cd companion-ai
COMPANION_LITE_MODE=true python -m persona_engine
# → http://localhost:8001/docs

# 方式 2：在你自己的代码里 import 用
```

## 最小用法

```python
from datetime import datetime
from persona_engine.persona_store import get_persona_profile, list_available_personas
from persona_engine.tone_generator import ToneGenerator
from shared_contracts import EmotionState, EmotionTag
from shared.models import RelationshipMetrics

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
