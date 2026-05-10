# shared_contracts

> 零依赖契约层 · 任何第三方数字生命宿主都能直接拿走的纯数据契约。

## 我是什么

`shared_contracts` 是 V2 重构波次 1 落地的**契约层**包，由三类纯定义组成：

- **数据模型**（Pydantic）：`UserProfile` / `TurnContext` / `EmotionState` / `EmotionTag` / `PersonaProfile` / `MemoryEntry` / `MemoryRecallResult` / `ActionSequence` / `VoiceSynthesisRequest` / `VoiceTranscriptionResult` / `DeviceInfo` / `MessagePayload`
- **事件类型**：`TurnStartEvent` / `TurnEndEvent` / `MemorySyncEvent` / `ActionGenerateEvent` / `VoiceSynthesizeEvent` / `PersonaUpdateEvent` / `DeviceCommandEvent`
- **协议接口**（`@runtime_checkable Protocol`）：`LLMClient` / `ASRProvider` / `TTSProvider`

ADR-006 硬约束：**本包零运行时副作用**，禁止 import 任何业务模块或 `shared_runtime`。

> 当前实现是 re-export shim（透传 `shared.models` / `shared.events` / 本包 `protocols.py`）；V2.1 起物理迁入。

## 暴露什么 API

```python
from shared_contracts import (
    # 模型
    UserProfile, TurnContext, EmotionState, EmotionTag,
    PersonaProfile, MemoryEntry, MemoryRecallResult,
    ActionSequence, VoiceSynthesisRequest, VoiceTranscriptionResult,
    DeviceInfo, MessagePayload,
    # 事件
    TurnStartEvent, TurnEndEvent, MemorySyncEvent,
    ActionGenerateEvent, VoiceSynthesizeEvent,
    PersonaUpdateEvent, DeviceCommandEvent,
    # 协议
    LLMClient, ASRProvider, TTSProvider,
)
```

## 依赖什么

- companion-ai 内部：仅 re-export `shared.models` / `shared.events`
- 第三方：`pydantic`（模型定义需要），无网络/数据库/文件系统副作用

## 怎么单独启

```bash
cd companion-ai
python -m shared_contracts
# 打印当前对外暴露的契约清单
```

## 最小用法

```python
from shared_contracts import EmotionTag, EmotionState, LLMClient

state = EmotionState(
    primary=EmotionTag.HAPPY,
    intensity=0.7, valence=0.5, arousal=0.4,
)

def handle(client: LLMClient):  # 只信 Protocol，宿主可注入自家实现
    assert isinstance(client, LLMClient)
```

## 第三方宿主接入提示

业务模块应**只 import 本包**（不要直接 import `shared.models`），这样宿主可以在自家工程里只复制 `shared_contracts/` 这一个零依赖包当 SDK 用。
