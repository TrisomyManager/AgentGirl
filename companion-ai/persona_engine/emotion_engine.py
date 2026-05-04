"""Emotion state machine with transition rules.

Rules:
- Events trigger emotion changes (user_message sentiment, memory recall, time of day).
- Emotions decay toward baseline over time.
- Intensity is modulated by relationship intimacy.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import structlog

from shared.models import EmotionState, EmotionTag, RelationshipMetrics

logger = structlog.get_logger("persona_engine.emotion_engine")

# ---------------------------------------------------------------------------
# Transition graph: which emotions can follow which, with directional bias.
# ---------------------------------------------------------------------------
_TRANSITION_GRAPH: Dict[EmotionTag, List[EmotionTag]] = {
    EmotionTag.NEUTRAL: [
        EmotionTag.HAPPY,
        EmotionTag.SAD,
        EmotionTag.SURPRISED,
        EmotionTag.CONCERNED,
        EmotionTag.CALM,
        EmotionTag.AFFECTIONATE,
    ],
    EmotionTag.HAPPY: [
        EmotionTag.EXCITED,
        EmotionTag.AFFECTIONATE,
        EmotionTag.CALM,
        EmotionTag.SURPRISED,
        EmotionTag.NEUTRAL,
    ],
    EmotionTag.SAD: [
        EmotionTag.CONCERNED,
        EmotionTag.CALM,
        EmotionTag.NEUTRAL,
        EmotionTag.AFFECTIONATE,
    ],
    EmotionTag.ANGRY: [
        EmotionTag.SAD,
        EmotionTag.CONCERNED,
        EmotionTag.NEUTRAL,
        EmotionTag.CALM,
    ],
    EmotionTag.SURPRISED: [
        EmotionTag.HAPPY,
        EmotionTag.EXCITED,
        EmotionTag.CONCERNED,
        EmotionTag.NEUTRAL,
        EmotionTag.CALM,
    ],
    EmotionTag.FEARFUL: [
        EmotionTag.CONCERNED,
        EmotionTag.SAD,
        EmotionTag.CALM,
        EmotionTag.NEUTRAL,
    ],
    EmotionTag.DISGUSTED: [
        EmotionTag.ANGRY,
        EmotionTag.SAD,
        EmotionTag.NEUTRAL,
        EmotionTag.CONCERNED,
    ],
    EmotionTag.AFFECTIONATE: [
        EmotionTag.HAPPY,
        EmotionTag.CALM,
        EmotionTag.EXCITED,
        EmotionTag.SURPRISED,
        EmotionTag.NEUTRAL,
    ],
    EmotionTag.CONCERNED: [
        EmotionTag.SAD,
        EmotionTag.CALM,
        EmotionTag.NEUTRAL,
        EmotionTag.AFFECTIONATE,
    ],
    EmotionTag.EXCITED: [
        EmotionTag.HAPPY,
        EmotionTag.SURPRISED,
        EmotionTag.AFFECTIONATE,
        EmotionTag.CALM,
        EmotionTag.NEUTRAL,
    ],
    EmotionTag.CALM: [
        EmotionTag.HAPPY,
        EmotionTag.AFFECTIONATE,
        EmotionTag.NEUTRAL,
        EmotionTag.CONCERNED,
        EmotionTag.SURPRISED,
    ],
}

# ---------------------------------------------------------------------------
# Sentiment → emotion mapping
# ---------------------------------------------------------------------------
_POSITIVE_MAP: List[Tuple[EmotionTag, float]] = [
    (EmotionTag.HAPPY, 0.40),
    (EmotionTag.AFFECTIONATE, 0.30),
    (EmotionTag.EXCITED, 0.20),
    (EmotionTag.SURPRISED, 0.10),
]

_NEGATIVE_MAP: List[Tuple[EmotionTag, float]] = [
    (EmotionTag.CONCERNED, 0.35),
    (EmotionTag.SAD, 0.30),
    (EmotionTag.FEARFUL, 0.20),
    (EmotionTag.ANGRY, 0.15),
]

_NEUTRAL_MAP: List[Tuple[EmotionTag, float]] = [
    (EmotionTag.CALM, 0.35),
    (EmotionTag.NEUTRAL, 0.35),
    (EmotionTag.SURPRISED, 0.15),
    (EmotionTag.HAPPY, 0.15),
]

# Decay constants
_DECAY_HALF_LIFE_MINUTES = 30.0  # emotion decays 50 % every 30 min
_BASELINE_PULL_RATE = 0.05       # per minute, linear pull toward baseline


def _weighted_choice(options: List[Tuple[EmotionTag, float]]) -> EmotionTag:
    tags, weights = zip(*options)
    return random.choices(tags, weights=weights, k=1)[0]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class EmotionEngine:
    """Stateful emotion engine per user.

    The engine keeps the *current* emotion in Redis (fast access) and
    applies transition rules on every user interaction or scheduled tick.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._baseline = EmotionState(
            primary=EmotionTag.CALM,
            intensity=0.4,
            valence=0.3,
            arousal=0.3,
            trigger="baseline",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_current_emotion(self, user_id: str) -> EmotionState:
        """Fetch current emotion from Redis (or in-memory fallback) or return baseline."""
        if self._redis is not None:
            key = f"persona:emotion:{user_id}"
            raw = await self._redis.hgetall(key)
            if raw:
                def _get(k: str, default: str) -> str:
                    v = raw.get(k)
                    return v.decode() if isinstance(v, bytes) else (v or default)

                try:
                    return EmotionState(
                        primary=EmotionTag(_get("primary", self._baseline.primary.value)),
                        intensity=float(_get("intensity", "0.4")),
                        valence=float(_get("valence", "0.0")),
                        arousal=float(_get("arousal", "0.3")),
                        timestamp=datetime.fromisoformat(_get("timestamp", datetime.utcnow().isoformat())),
                        trigger=_get("trigger", "baseline"),
                    )
                except Exception as exc:
                    logger.warning("emotion.parse_failed", user_id=user_id, error=str(exc))
                    return self._baseline

        # In-memory fallback
        if hasattr(self, "_memory_store") and user_id in self._memory_store:
            return self._memory_store[user_id]

        return self._baseline

    async def set_emotion(self, user_id: str, state: EmotionState) -> None:
        """Persist emotion to Redis (or in-memory fallback when Redis is absent)."""
        if self._redis is not None:
            key = f"persona:emotion:{user_id}"
            payload = {
                "primary": state.primary.value,
                "intensity": str(state.intensity),
                "valence": str(state.valence),
                "arousal": str(state.arousal),
                "timestamp": state.timestamp.isoformat(),
                "trigger": state.trigger or "",
            }
            await self._redis.hset(key, mapping=payload)
            await self._redis.expire(key, 86_400)
        else:
            # In-memory fallback for testing / local dev
            if not hasattr(self, "_memory_store"):
                self._memory_store: Dict[str, EmotionState] = {}
            self._memory_store[user_id] = state

    async def transition_from_user_message(
        self,
        user_id: str,
        sentiment: str,  # "positive" | "negative" | "neutral"
        relationship: RelationshipMetrics,
        message_content: str = "",
    ) -> EmotionState:
        """Compute a new emotion given the sentiment of a user message."""
        current = await self.get_current_emotion(user_id)
        intimacy = relationship.intimacy

        # 1. Pick candidate from sentiment map
        if sentiment == "positive":
            candidate = _weighted_choice(_POSITIVE_MAP)
        elif sentiment == "negative":
            candidate = _weighted_choice(_NEGATIVE_MAP)
        else:
            candidate = _weighted_choice(_NEUTRAL_MAP)

        # 2. If candidate is not in the transition graph from current primary,
        #    prefer a reachable emotion (keeps state machine coherent).
        reachable = _TRANSITION_GRAPH.get(current.primary, [])
        if reachable and candidate not in reachable:
            # Pick the closest reachable emotion by valence similarity.
            # If current is ANGRY and candidate is AFFECTIONATE (valence +0.8),
            # reachable emotions are SAD(-0.6), CONCERNED(-0.3), NEUTRAL(0.0), CALM(0.2).
            # The closest by valence is CALM(0.2), which is a safe stepping-stone.
            candidate = min(
                reachable,
                key=lambda e: abs(_emotion_valence(e) - _emotion_valence(candidate)),
            )

        # 3. Intensity modulation by intimacy
        #    Higher intimacy → emotions felt more deeply (intensity up).
        base_intensity = 0.5 + (intimacy * 0.3)  # 0.5 → 0.8
        # Random micro-variation for lifelike feel
        micro = random.uniform(-0.08, 0.08)
        new_intensity = _clamp(base_intensity + micro)

        # 4. Valence / arousal derived from the target emotion
        target_valence, target_arousal = _emotion_valence(candidate), _emotion_arousal(candidate)
        # Blend 70 % target, 30 % current (smooth transitions)
        new_valence = _clamp(target_valence * 0.7 + current.valence * 0.3 + random.uniform(-0.05, 0.05))
        new_arousal = _clamp(target_arousal * 0.7 + current.arousal * 0.3 + random.uniform(-0.05, 0.05))

        new_state = EmotionState(
            primary=candidate,
            intensity=new_intensity,
            valence=new_valence,
            arousal=new_arousal,
            timestamp=datetime.utcnow(),
            trigger=f"user_msg:{sentiment}",
        )
        await self.set_emotion(user_id, new_state)
        logger.info(
            "emotion.transition",
            user_id=user_id,
            from_emotion=current.primary.value,
            to_emotion=new_state.primary.value,
            sentiment=sentiment,
            intimacy=round(intimacy, 2),
        )
        return new_state

    async def transition_from_memory_recall(
        self,
        user_id: str,
        memory_emotion_tags: List[EmotionTag],
        relationship: RelationshipMetrics,
    ) -> EmotionState:
        """Shift emotion based on recalled memories."""
        current = await self.get_current_emotion(user_id)
        if not memory_emotion_tags:
            return current

        # Average valence of recalled memories
        avg_valence = sum(_emotion_valence(e) for e in memory_emotion_tags) / len(memory_emotion_tags)

        # Pull current valence 30 % toward memory valence
        new_valence = _clamp(current.valence * 0.7 + avg_valence * 0.3)

        # Pick closest emotion to new valence that is reachable
        reachable = _TRANSITION_GRAPH.get(current.primary, list(EmotionTag))
        best = min(reachable, key=lambda e: abs(_emotion_valence(e) - new_valence))

        intimacy_boost = relationship.intimacy * 0.15
        new_state = EmotionState(
            primary=best,
            intensity=_clamp(current.intensity + intimacy_boost + random.uniform(-0.05, 0.05)),
            valence=new_valence,
            arousal=_clamp(current.arousal + random.uniform(-0.1, 0.1)),
            timestamp=datetime.utcnow(),
            trigger="memory_recall",
        )
        await self.set_emotion(user_id, new_state)
        return new_state

    async def transition_from_time_of_day(
        self,
        user_id: str,
        hour: Optional[int] = None,
    ) -> EmotionState:
        """Apply gentle time-of-day modulation (e.g., calmer at night)."""
        current = await self.get_current_emotion(user_id)
        h = hour if hour is not None else datetime.utcnow().hour

        # Night hours → calmer, lower arousal
        if 22 <= h or h <= 5:
            target = EmotionTag.CALM
            arousal_delta = -0.15
        elif 6 <= h <= 9:
            target = EmotionTag.HAPPY
            arousal_delta = 0.10
        elif 17 <= h <= 20:
            target = EmotionTag.AFFECTIONATE
            arousal_delta = 0.05
        else:
            # Mid-day: slight random drift
            return current

        reachable = _TRANSITION_GRAPH.get(current.primary, [])
        if target not in reachable:
            target = current.primary  # stay put if not reachable

        new_state = EmotionState(
            primary=target,
            intensity=_clamp(current.intensity + random.uniform(-0.05, 0.05)),
            valence=_clamp(current.valence + random.uniform(-0.05, 0.05)),
            arousal=_clamp(current.arousal + arousal_delta),
            timestamp=datetime.utcnow(),
            trigger=f"time_of_day:{h}",
        )
        await self.set_emotion(user_id, new_state)
        return new_state

    async def decay_toward_baseline(self, user_id: str) -> EmotionState:
        """Apply time-based decay toward the persona's emotional baseline.

        Should be called periodically (e.g., by a background task or cron).
        """
        current = await self.get_current_emotion(user_id)
        baseline = self._baseline

        now = datetime.utcnow()
        elapsed_min = (now - current.timestamp).total_seconds() / 60.0
        if elapsed_min <= 0:
            return current

        # Exponential decay factor
        decay_factor = 1.0 - (0.5 ** (elapsed_min / _DECAY_HALF_LIFE_MINUTES))
        # Linear baseline pull
        pull = _BASELINE_PULL_RATE * elapsed_min

        new_intensity = _clamp(
            current.intensity + (baseline.intensity - current.intensity) * decay_factor
        )
        new_valence = _clamp(
            current.valence + (baseline.valence - current.valence) * decay_factor + random.uniform(-0.02, 0.02)
        )
        new_arousal = _clamp(
            current.arousal + (baseline.arousal - current.arousal) * decay_factor - pull
        )

        # If we are very close to baseline, snap to baseline primary
        if abs(new_valence - baseline.valence) < 0.05 and abs(new_arousal - baseline.arousal) < 0.05:
            primary = baseline.primary
        else:
            # Pick the emotion closest to the new valence/arousal coordinates
            primary = min(
                list(EmotionTag),
                key=lambda e: (_emotion_valence(e) - new_valence) ** 2
                + (_emotion_arousal(e) - new_arousal) ** 2,
            )

        new_state = EmotionState(
            primary=primary,
            intensity=new_intensity,
            valence=new_valence,
            arousal=new_arousal,
            timestamp=now,
            trigger="decay",
        )
        await self.set_emotion(user_id, new_state)
        logger.debug(
            "emotion.decay",
            user_id=user_id,
            elapsed_min=round(elapsed_min, 1),
            new_primary=primary.value,
        )
        return new_state


# ---------------------------------------------------------------------------
# Helpers: canonical valence / arousal for each EmotionTag
# ---------------------------------------------------------------------------

_EMOTION_VA: Dict[EmotionTag, Tuple[float, float]] = {
    EmotionTag.NEUTRAL: (0.0, 0.3),
    EmotionTag.HAPPY: (0.7, 0.6),
    EmotionTag.SAD: (-0.6, 0.2),
    EmotionTag.ANGRY: (-0.7, 0.8),
    EmotionTag.SURPRISED: (0.1, 0.8),
    EmotionTag.FEARFUL: (-0.6, 0.7),
    EmotionTag.DISGUSTED: (-0.5, 0.5),
    EmotionTag.AFFECTIONATE: (0.8, 0.4),
    EmotionTag.CONCERNED: (-0.3, 0.5),
    EmotionTag.EXCITED: (0.8, 0.9),
    EmotionTag.CALM: (0.2, 0.1),
}


def _emotion_valence(tag: EmotionTag) -> float:
    return _EMOTION_VA.get(tag, (0.0, 0.3))[0]


def _emotion_arousal(tag: EmotionTag) -> float:
    return _EMOTION_VA.get(tag, (0.0, 0.3))[1]
