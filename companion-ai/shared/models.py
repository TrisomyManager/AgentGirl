"""Shared Pydantic models for all companion-ai modules."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

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
    device_id: Optional[str] = Field(default=None, description="Current device identifier")
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
    trigger: Optional[str] = Field(default=None, description="What triggered this emotion")


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
    age_hint: Optional[int] = Field(default=None)
    gender_hint: Optional[str] = Field(default=None)
    core_traits: List[str] = Field(default_factory=list)
    communication_style: str = Field(default="", description="How they speak")
    values: List[str] = Field(default_factory=list)
    backstory: str = Field(default="", description="Origin / life story")
    relationship_goals: List[str] = Field(default_factory=list)
    emotional_baseline: EmotionState = Field(default_factory=EmotionState)
    voice_preference: Optional[str] = Field(default=None, description="TTS voice ID")
    avatar_2d_url: Optional[str] = Field(default=None)
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
    voice_duration_ms: Optional[int] = Field(default=None)
    has_image: bool = Field(default=False)
    image_urls: List[str] = Field(default_factory=list)
    device_info: Optional["DeviceInfo"] = Field(default=None)


class MemoryEntry(BaseModel):
    """A single entry in long-term memory."""
    entry_id: str
    user_id: str
    category: MemoryCategory
    content: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    emotion_tags: List[EmotionTag] = Field(default_factory=list)
    source_turn_id: Optional[str] = Field(default=None)
    embedding: Optional[List[float]] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(default=None)


class WorkingMemorySnapshot(BaseModel):
    """Compact representation of a session's working memory for prompt use.

    See ``memory_system/working.py`` for the producer side.
    """

    session_id: str
    turn_count: int = 0
    user_name: Optional[str] = Field(default=None)
    user_role: Optional[str] = Field(default=None)
    likes: List[str] = Field(default_factory=list)
    dislikes: List[str] = Field(default_factory=list)
    dominant_topic: Optional[str] = Field(default=None)
    dominant_topic_heuristic: Optional[str] = Field(
        default=None,
        description="Bag-of-words topic before optional LLM refinement (debug / UI).",
    )
    session_digest: Optional[str] = Field(
        default=None,
        description="Optional one-line LLM summary of recent in-window turns for the prompt.",
    )
    last_user_emotion: Optional[str] = Field(default=None)
    last_assistant_preview: Optional[str] = Field(default=None)
    recent_turns: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Oldest → newest list of {user_message, assistant_message, ...}.",
    )


class MemoryRecallResult(BaseModel):
    """Result of a memory recall query."""
    entries: List[MemoryEntry]
    graph_facts: List[str] = Field(default_factory=list)
    relationship_snapshot: Optional[RelationshipMetrics] = Field(default=None)
    user_profile_summary: Optional[str] = Field(default=None)
    working_memory: Optional[WorkingMemorySnapshot] = Field(
        default=None,
        description="Per-session rolling context surfaced from working memory.",
    )


class ActionFrame(BaseModel):
    """A single frame in an action sequence."""
    frame_id: str
    action_type: ActionType
    image_url: Optional[str] = Field(default=None)
    lip_shape: Optional[str] = Field(default=None)
    duration_ms: int = Field(default=100)
    emotion: EmotionTag = Field(default=EmotionTag.NEUTRAL)


class ActionSequence(BaseModel):
    """Full action sequence generated for a turn."""
    sequence_id: str
    turn_id: str
    frames: List[ActionFrame]
    total_duration_ms: int
    tts_audio_url: Optional[str] = Field(default=None)


class VoiceSynthesisRequest(BaseModel):
    """Request to synthesize speech."""
    text: str
    voice_id: Optional[str] = Field(default=None)
    emotion: EmotionTag = Field(default=EmotionTag.NEUTRAL)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = Field(default="zh-CN")


class VoiceTranscriptionResult(BaseModel):
    """Result of ASR transcription."""
    text: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    detected_emotion: EmotionTag = Field(default=EmotionTag.NEUTRAL)
    speaker_id: Optional[str] = Field(default=None)
    language: str = Field(default="zh-CN")
    duration_ms: int


class DeviceInfo(BaseModel):
    """Information about a connected device."""
    device_id: str
    user_id: str
    device_type: DeviceType
    device_name: str
    platform: Platform
    capabilities: List[str] = Field(default_factory=list)
    is_online: bool = Field(default=True)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    ip_address: Optional[str] = Field(default=None)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MessagePayload(BaseModel):
    """Standard message payload sent to/from gateways."""
    message_id: str
    session_id: str
    user_id: str
    platform: Platform
    content: str
    emotion: EmotionTag = Field(default=EmotionTag.NEUTRAL)
    action_sequence: Optional[ActionSequence] = Field(default=None)
    voice_url: Optional[str] = Field(default=None)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)
