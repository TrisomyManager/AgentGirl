"""Companion AI — Shared contracts and utilities."""

from .models import *
from .events import *
from .config import Settings, get_settings

__all__ = [
    # models
    "UserProfile",
    "TurnContext",
    "EmotionState",
    "PersonaProfile",
    "MemoryEntry",
    "MemoryRecallResult",
    "ActionSequence",
    "VoiceSynthesisRequest",
    "VoiceTranscriptionResult",
    "DeviceInfo",
    "MessagePayload",
    # events
    "TurnStartEvent",
    "TurnEndEvent",
    "MemorySyncEvent",
    "ActionGenerateEvent",
    "VoiceSynthesizeEvent",
    "PersonaUpdateEvent",
    "DeviceCommandEvent",
    # config
    "Settings",
    "get_settings",
]
