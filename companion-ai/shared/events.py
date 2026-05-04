"""Event types for the Redis Pub/Sub event bus.

All modules publish/consume events through the central event bus.
Events are JSON-serialized Pydantic models.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .models import (
    ActionSequence,
    DeviceInfo,
    EmotionState,
    EmotionTag,
    MemoryEntry,
    Platform,
    RelationshipMetrics,
    UserProfile,
    VoiceSynthesisRequest,
    VoiceTranscriptionResult,
)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class BaseEvent(BaseModel):
    """All events carry a unique ID and timestamp."""
    event_id: str = Field(..., description="UUID v4")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source_module: str = Field(..., description="Module that emitted the event")


# ---------------------------------------------------------------------------
# Turn lifecycle
# ---------------------------------------------------------------------------

class TurnStartEvent(BaseEvent):
    """Emitted by gateway_adapter when a new user turn begins."""
    event_type: str = Field(default="turn:start", frozen=True)
    turn_id: str
    session_id: str
    user: UserProfile
    user_message: str
    platform: Platform
    has_voice: bool = False
    voice_data_b64: Optional[str] = None
    has_image: bool = False
    image_urls: List[str] = Field(default_factory=list)
    device_info: Optional[DeviceInfo] = None


class TurnEndEvent(BaseEvent):
    """Emitted by core_orchestrator when a turn completes."""
    event_type: str = Field(default="turn:end", frozen=True)
    turn_id: str
    session_id: str
    user_id: str
    assistant_message: str
    emotion: EmotionTag
    action_sequence: Optional[ActionSequence] = None
    voice_url: Optional[str] = None
    memory_entries_created: List[MemoryEntry] = Field(default_factory=list)
    relationship_delta: Optional[RelationshipMetrics] = None


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemorySyncEvent(BaseEvent):
    """Emitted by core_orchestrator to trigger memory storage."""
    event_type: str = Field(default="memory:sync", frozen=True)
    turn_id: str
    user_id: str
    user_message: str
    assistant_message: str
    emotion: EmotionTag
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryRecallEvent(BaseEvent):
    """Emitted internally when a module requests memory recall."""
    event_type: str = Field(default="memory:recall", frozen=True)
    query: str
    user_id: str
    session_id: str
    top_k: int = Field(default=5, ge=1, le=50)
    include_graph: bool = True


# ---------------------------------------------------------------------------
# Persona / Emotion
# ---------------------------------------------------------------------------

class PersonaUpdateEvent(BaseEvent):
    """Emitted when persona state changes (emotion, relationship metrics)."""
    event_type: str = Field(default="persona:update", frozen=True)
    user_id: str
    new_emotion: EmotionState
    relationship_metrics: Optional[RelationshipMetrics] = None
    persona_delta: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Action / Voice
# ---------------------------------------------------------------------------

class ActionGenerateEvent(BaseEvent):
    """Emitted by core_orchestrator to request action generation."""
    event_type: str = Field(default="action:generate", frozen=True)
    turn_id: str
    user_id: str
    assistant_message: str
    emotion: EmotionTag
    reference_image_url: Optional[str] = None


class VoiceSynthesizeEvent(BaseEvent):
    """Emitted by core_orchestrator to request TTS."""
    event_type: str = Field(default="voice:synthesize", frozen=True)
    turn_id: str
    user_id: str
    request: VoiceSynthesisRequest


class VoiceTranscribeEvent(BaseEvent):
    """Emitted when voice data needs transcription."""
    event_type: str = Field(default="voice:transcribe", frozen=True)
    turn_id: str
    user_id: str
    audio_data_b64: str
    language: str = "zh-CN"


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------

class DeviceCommandEvent(BaseEvent):
    """Emitted by core_orchestrator to send a command to a device."""
    event_type: str = Field(default="device:command", frozen=True)
    device_id: str
    user_id: str
    command: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class DeviceHeartbeatEvent(BaseEvent):
    """Emitted by device_coordination on each device heartbeat."""
    event_type: str = Field(default="device:heartbeat", frozen=True)
    device_info: DeviceInfo


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------

class GatewaySendEvent(BaseEvent):
    """Emitted to send a message through a specific platform gateway."""
    event_type: str = Field(default="gateway:send", frozen=True)
    user_id: str
    platform: Platform
    content: str
    voice_url: Optional[str] = None
    action_sequence: Optional[ActionSequence] = None
    reply_to_message_id: Optional[str] = None


class GatewayBroadcastEvent(BaseEvent):
    """Emitted to broadcast a message to all user's connected platforms."""
    event_type: str = Field(default="gateway:broadcast", frozen=True)
    user_id: str
    content: str
    exclude_platforms: List[Platform] = Field(default_factory=list)
