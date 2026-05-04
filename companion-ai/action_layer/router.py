"""Action routing logic.

Maps emotion + intent → ActionType, and ActionType → animation template.
"""

from typing import Any

import structlog

from shared.models import ActionType, EmotionTag

logger = structlog.get_logger("action_layer.router")

# ---------------------------------------------------------------------------
# Emotion + intent → ActionType mapping
# ---------------------------------------------------------------------------

_INTENT_ACTION_MAP: dict[str, ActionType] = {
    "greet": ActionType.GESTURE_WAVE,
    "farewell": ActionType.GESTURE_WAVE,
    "agree": ActionType.GESTURE_NOD,
    "confirm": ActionType.GESTURE_NOD,
    "think": ActionType.REACT_THINKING,
    "ponder": ActionType.REACT_THINKING,
    "listen": ActionType.LISTEN,
    "idle": ActionType.IDLE,
    "talk": ActionType.TALK,
}

_EMOTION_ACTION_MAP: dict[EmotionTag, ActionType] = {
    EmotionTag.HAPPY: ActionType.REACT_HAPPY,
    EmotionTag.SAD: ActionType.REACT_SAD,
    EmotionTag.SURPRISED: ActionType.REACT_SURPRISED,
    EmotionTag.EXCITED: ActionType.REACT_HAPPY,
    EmotionTag.AFFECTIONATE: ActionType.REACT_HAPPY,
    EmotionTag.ANGRY: ActionType.REACT_SAD,
    EmotionTag.FEARFUL: ActionType.REACT_SAD,
    EmotionTag.CONCERNED: ActionType.REACT_THINKING,
    EmotionTag.CALM: ActionType.IDLE,
    EmotionTag.NEUTRAL: ActionType.IDLE,
    EmotionTag.DISGUSTED: ActionType.REACT_SAD,
}

# ---------------------------------------------------------------------------
# ActionType → template metadata
# ---------------------------------------------------------------------------

_ACTION_TEMPLATES: dict[ActionType, dict[str, Any]] = {
    ActionType.IDLE: {
        "name": "idle",
        "description": "Neutral breathing idle pose",
        "frame_count": 12,
        "fps": 12,
        "loop": True,
        "has_lip_sync": False,
    },
    ActionType.TALK: {
        "name": "talk",
        "description": "Talking with natural body movement",
        "frame_count": 24,
        "fps": 12,
        "loop": True,
        "has_lip_sync": True,
    },
    ActionType.LISTEN: {
        "name": "listen",
        "description": "Attentive listening pose with slight head tilt",
        "frame_count": 18,
        "fps": 12,
        "loop": True,
        "has_lip_sync": False,
    },
    ActionType.REACT_HAPPY: {
        "name": "react_happy",
        "description": "Happy reaction — smile, slight bounce",
        "frame_count": 20,
        "fps": 12,
        "loop": False,
        "has_lip_sync": False,
    },
    ActionType.REACT_SAD: {
        "name": "react_sad",
        "description": "Sad reaction — droop shoulders, look down",
        "frame_count": 20,
        "fps": 12,
        "loop": False,
        "has_lip_sync": False,
    },
    ActionType.REACT_SURPRISED: {
        "name": "react_surprised",
        "description": "Surprised reaction — widen eyes, lean back",
        "frame_count": 16,
        "fps": 12,
        "loop": False,
        "has_lip_sync": False,
    },
    ActionType.REACT_THINKING: {
        "name": "react_thinking",
        "description": "Thinking pose — hand to chin, gaze up",
        "frame_count": 24,
        "fps": 12,
        "loop": True,
        "has_lip_sync": False,
    },
    ActionType.GESTURE_WAVE: {
        "name": "gesture_wave",
        "description": "Waving gesture",
        "frame_count": 16,
        "fps": 12,
        "loop": False,
        "has_lip_sync": False,
    },
    ActionType.GESTURE_NOD: {
        "name": "gesture_nod",
        "description": "Nodding gesture",
        "frame_count": 12,
        "fps": 12,
        "loop": False,
        "has_lip_sync": False,
    },
    ActionType.GESTURE_HEAD_TILT: {
        "name": "gesture_head_tilt",
        "description": "Head tilt curiosity gesture",
        "frame_count": 14,
        "fps": 12,
        "loop": False,
        "has_lip_sync": False,
    },
}


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class ActionRouter:
    """Routes emotion + intent to ActionType and resolves animation templates."""

    @staticmethod
    def resolve_action_type(intent: str | None, emotion: EmotionTag) -> ActionType:
        """Map intent and emotion to the most appropriate ActionType.

        Priority:
        1. Explicit intent match
        2. Emotion-driven reaction
        3. Fallback to TALK (if speaking) or IDLE
        """
        if intent:
            intent_lower = intent.lower().strip()
            if intent_lower in _INTENT_ACTION_MAP:
                action = _INTENT_ACTION_MAP[intent_lower]
                logger.info("router.intent_match", intent=intent, action=action.value)
                return action

        # Fallback to emotion
        action = _EMOTION_ACTION_MAP.get(emotion, ActionType.IDLE)
        logger.info("router.emotion_match", emotion=emotion.value, action=action.value)
        return action

    @staticmethod
    def get_template(action_type: ActionType) -> dict[str, Any]:
        """Get animation template metadata for an ActionType."""
        return _ACTION_TEMPLATES.get(action_type, _ACTION_TEMPLATES[ActionType.IDLE]).copy()

    @staticmethod
    def list_templates() -> list[dict[str, Any]]:
        """List all available action templates."""
        return [
            {"action_type": action.value, **meta}
            for action, meta in _ACTION_TEMPLATES.items()
        ]
