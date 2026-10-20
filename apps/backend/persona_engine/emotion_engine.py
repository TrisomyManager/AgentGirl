"""Continuous valence/arousal dynamics; discrete tags are presentation labels.

Transitions are deterministic and bounded. Reads decay from the last persisted
timestamp without writing, so refresh frequency cannot accelerate relaxation.
"""

from datetime import UTC, datetime

from shared_contracts.models import EmotionState, EmotionTag

_DECAY_HALF_LIFE_MINUTES = 30.0
_EMOTION_VA = {
    EmotionTag.NEUTRAL: (0.0, 0.3),
    EmotionTag.HAPPY: (0.7, 0.6),
    EmotionTag.SAD: (-0.6, 0.2),
    EmotionTag.ANGRY: (-0.7, 0.8),
    EmotionTag.SURPRISED: (0.1, 0.8),
    EmotionTag.FEARFUL: (-0.6, 0.7),
    EmotionTag.DISGUSTED: (-0.5, 0.5),
    EmotionTag.AFFECTIONATE: (0.8, 0.4),
    EmotionTag.CONCERNED: (-0.25, 0.45),
    EmotionTag.EXCITED: (0.8, 0.9),
    EmotionTag.CALM: (0.2, 0.1),
}


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def _emotion_valence(tag):
    return _EMOTION_VA.get(tag, (0.0, 0.3))[0]


def _emotion_arousal(tag):
    return _EMOTION_VA.get(tag, (0.0, 0.3))[1]


def label_for(valence, arousal, previous=None):
    distances = {tag: (v - valence) ** 2 + (a - arousal) ** 2 for tag, (v, a) in _EMOTION_VA.items()}
    best = min(distances, key=distances.get)
    # Small hysteresis prevents visible jitter at category boundaries.
    return previous if previous in distances and distances[previous] <= distances[best] + 0.008 else best


class EmotionEngine:
    def __init__(self, redis_client=None, *, state_store=None, baseline=None):
        self._redis = redis_client
        self.state_store = state_store
        self._memory_store = {}
        self._baseline = baseline or EmotionState(
            primary=EmotionTag.CALM, intensity=0.4, valence=0.3, arousal=0.3, trigger="baseline"
        )

    def relax(self, state, *, now=None, baseline=None):
        baseline = baseline or self._baseline
        now = utc(now or datetime.now(UTC))
        minutes = max(0.0, (now - utc(state.timestamp)).total_seconds() / 60)
        remaining = 0.5 ** (minutes / _DECAY_HALF_LIFE_MINUTES)
        valence = baseline.valence + (state.valence - baseline.valence) * remaining
        arousal = baseline.arousal + (state.arousal - baseline.arousal) * remaining
        return state.model_copy(
            update={
                "primary": label_for(valence, arousal, state.primary),
                "valence": valence,
                "arousal": arousal,
                "intensity": baseline.intensity + (state.intensity - baseline.intensity) * remaining,
                "timestamp": now,
            }
        )

    async def get_current_emotion(self, user_id):
        state = None
        if self.state_store:
            state = await self.state_store.get_emotion(user_id)
        elif self._redis is not None:
            raw = await self._redis.hgetall(f"persona:emotion:{user_id}")
            if raw:
                decoded = {
                    (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
                    for k, v in raw.items()
                }
                try:
                    state = EmotionState(**decoded)
                except ValueError:
                    state = None
        else:
            state = self._memory_store.get(user_id)
        return self.relax(state) if state else self._baseline.model_copy(update={"timestamp": datetime.now(UTC)})

    async def set_emotion(self, user_id, state):
        if self.state_store:
            await self.state_store.put_emotion(user_id, state)
        elif self._redis is not None:
            payload = {key: str(value) for key, value in state.model_dump(mode="json").items() if value is not None}
            await self._redis.hset(f"persona:emotion:{user_id}", mapping=payload)
            await self._redis.expire(f"persona:emotion:{user_id}", 86400)
        else:
            self._memory_store[user_id] = state.model_copy(deep=True)

    def predict(
        self,
        current,
        relationship,
        *,
        sentiment="neutral",
        valence=None,
        arousal=None,
        confidence=1.0,
        now=None,
        baseline=None,
    ):
        """Pure preview of one user reaction, also used inside atomic persistence."""
        current = self.relax(current or baseline or self._baseline, now=now, baseline=baseline)
        target_v, target_a = {"positive": (0.75, 0.65), "negative": (-0.6, 0.45)}.get(sentiment, (0.25, 0.3))
        target_v = target_v if valence is None else _clamp(valence, -1.0, 1.0)
        target_a = target_a if arousal is None else _clamp(arousal)
        strength = (0.5 + relationship.intimacy * 0.15) * _clamp(confidence, 0.2, 1.0)
        valence = _clamp(current.valence + _clamp((target_v - current.valence) * strength, -0.45, 0.45), -1, 1)
        arousal = _clamp(current.arousal + _clamp((target_a - current.arousal) * strength, -0.3, 0.3))
        intensity = _clamp(0.4 + abs(valence) * 0.3 + arousal * 0.2 + relationship.intimacy * 0.1)
        return EmotionState(
            primary=label_for(valence, arousal, current.primary),
            intensity=intensity,
            valence=valence,
            arousal=arousal,
            timestamp=current.timestamp,
            trigger=f"user_msg:{sentiment}",
        )

    async def transition_from_user_message(self, user_id, sentiment, relationship, message_content=""):
        current = await self.get_current_emotion(user_id)
        state = self.predict(current, relationship, sentiment=sentiment)
        await self.set_emotion(user_id, state)
        return state

    async def transition_from_memory_recall(self, user_id, memory_emotion_tags, relationship):
        current = await self.get_current_emotion(user_id)
        if not memory_emotion_tags:
            return current
        valence = (
            current.valence * 0.7
            + sum(_emotion_valence(e) for e in memory_emotion_tags) / len(memory_emotion_tags) * 0.3
        )
        arousal = (
            current.arousal * 0.7
            + sum(_emotion_arousal(e) for e in memory_emotion_tags) / len(memory_emotion_tags) * 0.3
        )
        state = current.model_copy(
            update={
                "primary": label_for(valence, arousal, current.primary),
                "valence": valence,
                "arousal": arousal,
                "trigger": "memory_recall",
            }
        )
        await self.set_emotion(user_id, state)
        return state

    async def transition_from_time_of_day(self, user_id, hour=None):
        current = await self.get_current_emotion(user_id)
        hour = datetime.now(UTC).hour if hour is None else hour
        if hour >= 22 or hour <= 5:
            arousal = max(0, current.arousal - 0.15)
        elif 6 <= hour <= 9:
            arousal = min(1, current.arousal + 0.1)
        else:
            return current
        state = current.model_copy(
            update={
                "primary": label_for(current.valence, arousal),
                "arousal": arousal,
                "trigger": f"time_of_day:{hour}",
            }
        )
        await self.set_emotion(user_id, state)
        return state

    async def decay_toward_baseline(self, user_id):
        state = (await self.get_current_emotion(user_id)).model_copy(update={"trigger": "decay"})
        await self.set_emotion(user_id, state)
        return state
