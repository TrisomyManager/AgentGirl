"""数据模型契约层 —— 业务模块共享的纯 Pydantic 模型.

P1-C 物理搬迁完成 (V2.1):
- 原 ``shared.models`` 的物理实现现在位于本文件
- ``shared.models`` 反向 re-export, 保留向后兼容
- 业务侧应优先 ``from shared_contracts import X``

ADR-006 硬约束 1: 契约层零运行时副作用, 仅 Pydantic + stdlib.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Platform(str, Enum):
    """Supported messaging / client platforms."""
    APP = "app"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WECHAT = "wechat"
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    WHATSAPP = "whatsapp"
    SLACK = "slack"
    EMAIL = "email"


class EmotionTag(str, Enum):
    """Discrete emotion tags used across the system."""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SURPRISED = "surprised"
    FEARFUL = "fearful"
    DISGUSTED = "disgusted"
    AFFECTIONATE = "affectionate"
    CONCERNED = "concerned"
    EXCITED = "excited"
    CALM = "calm"


class ActionType(str, Enum):
    """Types of actions the companion can perform."""
    IDLE = "idle"
    TALK = "talk"
    LISTEN = "listen"
    REACT_HAPPY = "react_happy"
    REACT_SAD = "react_sad"
    REACT_SURPRISED = "react_surprised"
    REACT_THINKING = "react_thinking"
    GESTURE_WAVE = "gesture_wave"
    GESTURE_NOD = "gesture_nod"
    GESTURE_HEAD_TILT = "gesture_head_tilt"


class MemoryCategory(str, Enum):
    """Categories for long-term memory entries."""
    FACT = "fact"
    EMOTION = "emotion"
    EVENT = "event"
    PREFERENCE = "preference"
    RELATIONSHIP_MILESTONE = "relationship_milestone"
    ROUTINE = "routine"


class DeviceType(str, Enum):
    """Types of devices in the ecosystem."""
    MOBILE = "mobile"
    TABLET = "tablet"
    PC = "pc"
    SMART_SPEAKER = "smart_speaker"
    SMART_DISPLAY = "smart_display"
    WEARABLE = "wearable"


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------

class UserProfile(BaseModel):
    """Minimal user identity used across modules."""
    user_id: str = Field(..., description="Global unique user ID")
    display_name: str = Field(default="", description="User's preferred name")
    platform: Platform = Field(default=Platform.APP)
    device_id: str | None = Field(default=None, description="Current device identifier")
    timezone: str = Field(default="UTC")
    language: str = Field(default="zh-CN")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EmotionState(BaseModel):
    """Real-time emotional state of the companion persona."""
    primary: EmotionTag = Field(default=EmotionTag.NEUTRAL)
    intensity: float = Field(default=0.5, ge=0.0, le=1.0, description="0-1 intensity")
    valence: float = Field(default=0.0, ge=-1.0, le=1.0, description="-1 negative to +1 positive")
    arousal: float = Field(default=0.5, ge=0.0, le=1.0, description="0 calm to 1 excited")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    trigger: str | None = Field(default=None, description="What triggered this emotion")


class RelationshipMetrics(BaseModel):
    """Relationship depth indicators for a single user."""
    user_id: str
    intimacy: float = Field(default=0.0, ge=0.0, le=1.0)
    trust: float = Field(default=0.0, ge=0.0, le=1.0)
    familiarity: float = Field(default=0.0, ge=0.0, le=1.0)
    affection: float = Field(default=0.0, ge=0.0, le=1.0)
    total_interactions: int = Field(default=0)
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)


class PersonaProfile(BaseModel):
    """Structured companion persona / soul definition."""
    persona_id: str = Field(default="default")
    name: str = Field(..., description="Companion's name")
    age_hint: int | None = Field(default=None)
    gender_hint: str | None = Field(default=None)
    core_traits: list[str] = Field(default_factory=list)
    communication_style: str = Field(default="", description="How they speak")
    values: list[str] = Field(default_factory=list)
    backstory: str = Field(default="", description="Origin / life story")
    relationship_goals: list[str] = Field(default_factory=list)
    emotional_baseline: EmotionState = Field(default_factory=EmotionState)
    voice_preference: str | None = Field(default=None, description="TTS voice ID")
    avatar_2d_url: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TurnContext(BaseModel):
    """Context for a single conversation turn."""
    turn_id: str = Field(..., description="Unique turn UUID")
    session_id: str = Field(..., description="Session UUID")
    user: UserProfile
    user_message: str = Field(..., description="Raw user input")
    platform: Platform
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    has_voice: bool = Field(default=False)
    request_voice_reply: bool = Field(default=False)
    voice_duration_ms: int | None = Field(default=None)
    has_image: bool = Field(default=False)
    image_urls: list[str] = Field(default_factory=list)
    device_info: DeviceInfo | None = Field(default=None)


class MemoryEntry(BaseModel):
    """A single entry in long-term memory."""
    entry_id: str
    user_id: str
    category: MemoryCategory
    content: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    emotion_tags: list[EmotionTag] = Field(default_factory=list)
    source_turn_id: str | None = Field(default=None)
    embedding: list[float] | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = Field(default=None)


class WorkingMemorySnapshot(BaseModel):
    """Compact representation of a session's working memory for prompt use.

    See ``memory_system/working.py`` for the producer side.
    """

    session_id: str
    turn_count: int = 0
    user_name: str | None = Field(default=None)
    user_role: str | None = Field(default=None)
    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    dominant_topic: str | None = Field(default=None)
    dominant_topic_heuristic: str | None = Field(
        default=None,
        description="Bag-of-words topic before optional LLM refinement (debug / UI).",
    )
    session_digest: str | None = Field(
        default=None,
        description="Optional one-line LLM summary of recent in-window turns for the prompt.",
    )
    last_user_emotion: str | None = Field(default=None)
    last_assistant_preview: str | None = Field(default=None)
    recent_turns: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Oldest → newest list of {user_message, assistant_message, ...}.",
    )


class MemoryRecallResult(BaseModel):
    """Result of a memory recall query."""
    entries: list[MemoryEntry]
    graph_facts: list[str] = Field(default_factory=list)
    relationship_snapshot: RelationshipMetrics | None = Field(default=None)
    user_profile_summary: str | None = Field(default=None)
    working_memory: WorkingMemorySnapshot | None = Field(
        default=None,
        description="Per-session rolling context surfaced from working memory.",
    )


class ActionFrame(BaseModel):
    """A single frame in an action sequence."""
    frame_id: str
    action_type: ActionType
    image_url: str | None = Field(default=None)
    lip_shape: str | None = Field(default=None)
    duration_ms: int = Field(default=100)
    emotion: EmotionTag = Field(default=EmotionTag.NEUTRAL)


class ActionSequence(BaseModel):
    """Full action sequence generated for a turn."""
    sequence_id: str
    turn_id: str
    frames: list[ActionFrame]
    total_duration_ms: int
    tts_audio_url: str | None = Field(default=None)


class VoiceSynthesisRequest(BaseModel):
    """Request to synthesize speech.

    ``voice_id`` can be either a logical ``voice_profile_id`` (e.g. ``"xiaonuan"``)
    or a provider-native voice ID (e.g. ``"zh-CN-XiaoxiaoNeural"``).  The
    voice_layer entrypoint always calls ``resolve_voice()`` to derive the
    actual provider-specific voice before passing it to the TTS backend.

    When ``voice_profile_id`` is set and ``voice_id`` is empty, the TTS client
    prefers ``voice_profile_id`` as the resolution target.
    """
    text: str
    voice_id: str | None = Field(
        default=None,
        description="Logical voice_profile_id or provider-native voice ID",
    )
    voice_profile_id: str | None = Field(default=None, description="Explicit logical voice_profile_id (preferred over voice_id)")
    emotion: EmotionTag = Field(default=EmotionTag.NEUTRAL)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = Field(default="zh-CN")


class VoiceTranscriptionResult(BaseModel):
    """Result of ASR transcription."""
    text: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    detected_emotion: EmotionTag = Field(default=EmotionTag.NEUTRAL)
    speaker_id: str | None = Field(default=None)
    language: str = Field(default="zh-CN")
    duration_ms: int


class VoiceProfile(BaseModel):
    """Unified voice profile that maps a character-level voice_id to provider-specific settings.

    Ordinary TTS and realtime voice MUST share the same VoiceProfile resolution.
    Provider-specific voice IDs (Azure, DashScope, Volc, Piper, etc.) are resolved
    from this profile — never hardcoded in business modules.
    """
    voice_profile_id: str = Field(..., description="Logical voice ID (e.g. 'default', 'huayan')")
    display_name: str = Field(default="Default Voice")
    provider_voices: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from provider name to provider-specific voice/speaker ID",
    )
    sample_rate: int = Field(default=22050, description="Preferred TTS sample rate")
    language: str = Field(default="zh-CN")


class DeviceInfo(BaseModel):
    """Information about a connected device."""
    device_id: str
    user_id: str
    device_type: DeviceType
    device_name: str
    platform: Platform
    capabilities: list[str] = Field(default_factory=list)
    is_online: bool = Field(default=True)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    ip_address: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessagePayload(BaseModel):
    """Standard message payload sent to/from gateways."""
    message_id: str
    session_id: str
    user_id: str
    platform: Platform
    content: str
    emotion: EmotionTag = Field(default=EmotionTag.NEUTRAL)
    action_sequence: ActionSequence | None = Field(default=None)
    voice_url: str | None = Field(default=None)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    # Enums
    "Platform",
    "EmotionTag",
    "ActionType",
    "MemoryCategory",
    "DeviceType",
    # Core models
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
]
