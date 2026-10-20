"""shared_contracts —— 零依赖契约层.

P1-C 物理搬迁完成 (V2.1):
- ``models`` / ``events`` 现在物理位于本包内, 不再从 ``shared`` re-export
- ``shared.models`` / ``shared.events`` 反向变成 deprecated shim, 旧兼容入口在 V2.22 已移除

依赖原则 (ADR-006 硬约束):
- 本包**禁止 import 任何业务模块** (persona_engine / memory_system / voice_layer / ...)
- 本包**禁止 import shared_runtime** (运行时与契约必须分层)
- 业务侧应优先 ``from shared_contracts import X``
"""

from __future__ import annotations

# --- 事件类型 (物理位于 shared_contracts.events) ---
from .events import (
    ActionGenerateEvent,
    BaseEvent,
    DeviceCommandEvent,
    DeviceHeartbeatEvent,
    GatewayBroadcastEvent,
    GatewaySendEvent,
    MemoryRecallEvent,
    MemorySyncEvent,
    PersonaUpdateEvent,
    TurnEndEvent,
    TurnStartEvent,
    VoiceSynthesizeEvent,
    VoiceTranscribeEvent,
)

# --- 数据模型 (物理位于 shared_contracts.models) ---
from .models import (
    ActionFrame,
    ActionSequence,
    ActionType,
    DeviceInfo,
    DeviceType,
    EmotionState,
    EmotionTag,
    MemoryCategory,
    MemoryEntry,
    MemoryRecallResult,
    MessagePayload,
    PersonaProfile,
    Platform,
    RelationshipMetrics,
    TurnContext,
    UserProfile,
    VoiceProfile,
    VoiceSynthesisRequest,
    VoiceTranscriptionResult,
    WorkingMemorySnapshot,
)
from .platforms import PlatformMessage

# --- Protocols (宿主可注入的运行时接口形状) ---
from .protocols import ASRProvider, LLMClient, MemoryReader, RealtimeVoiceProvider, SpeechRecognizer, TTSProvider

__all__ = [
    "PlatformMessage",
    # Enums
    "Platform",
    "EmotionTag",
    "ActionType",
    "MemoryCategory",
    "DeviceType",
    # Models
    "UserProfile",
    "EmotionState",
    "RelationshipMetrics",
    "PersonaProfile",
    "TurnContext",
    "MemoryEntry",
    "WorkingMemorySnapshot",
    "MemoryRecallResult",
    "ActionFrame",
    "ActionSequence",
    "VoiceSynthesisRequest",
    "VoiceTranscriptionResult",
    "VoiceProfile",
    "DeviceInfo",
    "MessagePayload",
    # Events
    "BaseEvent",
    "TurnStartEvent",
    "TurnEndEvent",
    "MemorySyncEvent",
    "MemoryRecallEvent",
    "PersonaUpdateEvent",
    "ActionGenerateEvent",
    "VoiceSynthesizeEvent",
    "VoiceTranscribeEvent",
    "DeviceCommandEvent",
    "DeviceHeartbeatEvent",
    "GatewaySendEvent",
    "GatewayBroadcastEvent",
    # Protocols
    "LLMClient",
    "ASRProvider",
    "SpeechRecognizer",
    "MemoryReader",
    "TTSProvider",
    "RealtimeVoiceProvider",
]
