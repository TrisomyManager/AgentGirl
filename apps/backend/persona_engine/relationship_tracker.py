"""Track and update RelationshipMetrics per user.

Metrics:
- intimacy:    personal disclosure, shared experiences
- trust:       consistent positive interactions
- familiarity: repeated topics / routines
- affection:   cumulative warmth

Decay applies if no interaction for an extended period.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from persona_engine.emotion_engine import utc
from persona_engine.state_store import PersonaStateStore
from shared_contracts.models import RelationshipMetrics

logger = structlog.get_logger("persona_engine.relationship_tracker")

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------
_INTIMACY_PER_DISCLOSURE = 0.03
_INTIMACY_PER_SHARED_EXPERIENCE = 0.02
_TRUST_PER_POSITIVE_INTERACTION = 0.015
_FAMILIARITY_PER_ROUTINE = 0.02
_AFFECTION_PER_WARMTH_SIGNAL = 0.01

# Decay per day of inactivity
_DECAY_DAILY = {
    "intimacy": 0.005,
    "trust": 0.002,
    "familiarity": 0.003,
    "affection": 0.004,
}

# Floor values — relationships never fully reset to zero
_DECAY_FLOOR = {
    "intimacy": 0.05,
    "trust": 0.10,
    "familiarity": 0.10,
    "affection": 0.05,
}


class RelationshipTracker:
    """Manages per-user relationship metrics backed by PostgreSQL + Redis cache,
    with SQLite fallback for lite mode."""

    def __init__(self, redis_client=None, db_pool=None, sqlite_session_factory=None, *, state_store=None):
        self._redis = redis_client
        self._db = db_pool  # asyncpg pool (PostgreSQL)
        self._sqlite_session_factory: Callable[[], AsyncSession] | None = sqlite_session_factory
        self._sqlite_schema_initialized = False
        self.state_store = state_store or (
            PersonaStateStore(sqlite_session_factory) if sqlite_session_factory else None
        )
        self._memory_store = {}

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_metrics(self, user_id: str) -> RelationshipMetrics:
        """Return current metrics, preferring Redis cache."""
        if self.state_store:
            return self._apply_decay(await self.state_store.get_relationship(user_id))
        if self._redis is None and self._db is None and user_id in self._memory_store:
            return self._apply_decay(self._memory_store[user_id])
        cached = await self._from_redis(user_id)
        if cached:
            # Apply decay if stale
            cached = self._apply_decay(cached)
            return cached

        # PostgreSQL (asyncpg)
        if self._db:
            row = await self._db.fetchrow("SELECT * FROM relationship_metrics WHERE user_id = $1", user_id)
            if row:
                metrics = RelationshipMetrics(
                    user_id=row["user_id"],
                    intimacy=float(row["intimacy"]),
                    trust=float(row["trust"]),
                    familiarity=float(row["familiarity"]),
                    affection=float(row["affection"]),
                    total_interactions=int(row["total_interactions"]),
                    first_seen=row["first_seen"],
                    last_seen=row["last_seen"],
                )
                await self._to_redis(user_id, metrics)
                return self._apply_decay(metrics)

        # SQLite (SQLAlchemy async session)
        if self._sqlite_session_factory:
            await self._init_sqlite_schema()
            async with self._sqlite_session_factory() as session:
                result = await session.execute(
                    text("SELECT * FROM relationship_metrics WHERE user_id = :user_id"),
                    {"user_id": user_id},
                )
                row = result.mappings().first()
                if row:
                    metrics = RelationshipMetrics(
                        user_id=row["user_id"],
                        intimacy=float(row["intimacy"]),
                        trust=float(row["trust"]),
                        familiarity=float(row["familiarity"]),
                        affection=float(row["affection"]),
                        total_interactions=int(row["total_interactions"]),
                        first_seen=row["first_seen"],
                        last_seen=row["last_seen"],
                    )
                    metrics = self._apply_decay(metrics)
                    await self._to_redis(user_id, metrics)
                    return metrics

        # First time seeing this user
        now = datetime.utcnow()
        metrics = RelationshipMetrics(
            user_id=user_id,
            first_seen=now,
            last_seen=now,
        )
        await self._to_redis(user_id, metrics)
        await self._persist(metrics)
        return metrics

    # ------------------------------------------------------------------
    # Update rules
    # ------------------------------------------------------------------

    async def record_interaction(
        self,
        user_id: str,
        sentiment: str = "neutral",
        has_disclosure: bool = False,
        is_routine: bool = False,
        shared_experience: bool = False,
        hostile: bool = False,
        event_id: str | None = None,
    ) -> RelationshipMetrics:
        """Update metrics after a single interaction."""
        if self.state_store:
            _, metrics = await self.state_store.update(
                user_id,
                lambda emotion, relationship: (
                    emotion,
                    apply_interaction(
                        self._apply_decay(relationship),
                        sentiment=sentiment,
                        has_disclosure=has_disclosure,
                        is_routine=is_routine,
                        shared_experience=shared_experience,
                        hostile=hostile,
                    ),
                ),
                event_id=f"interaction:{event_id}" if event_id else None,
            )
            return metrics
        metrics = await self.get_metrics(user_id)
        metrics = apply_interaction(
            metrics,
            sentiment=sentiment,
            has_disclosure=has_disclosure,
            is_routine=is_routine,
            shared_experience=shared_experience,
            hostile=hostile,
        )

        await self._to_redis(user_id, metrics)
        await self._persist(metrics)
        logger.info(
            "relationship.updated",
            user_id=user_id,
            total_interactions=metrics.total_interactions,
            intimacy=round(metrics.intimacy, 3),
            trust=round(metrics.trust, 3),
            familiarity=round(metrics.familiarity, 3),
            affection=round(metrics.affection, 3),
        )
        return metrics

    async def record_milestone(
        self,
        user_id: str,
        milestone_type: str,  # e.g. "first_voice_call", "shared_secret", "anniversary"
        *,
        event_id: str | None = None,
    ) -> RelationshipMetrics:
        """Apply a larger step change for relationship milestones."""
        if self.state_store:
            _, metrics = await self.state_store.update(
                user_id,
                lambda emotion, relationship: (
                    emotion,
                    apply_milestone(self._apply_decay(relationship), milestone_type),
                ),
                event_id=f"milestone:{event_id}" if event_id else None,
            )
            return metrics
        metrics = await self.get_metrics(user_id)
        metrics = apply_milestone(metrics, milestone_type)

        await self._to_redis(user_id, metrics)
        await self._persist(metrics)
        logger.info("relationship.milestone", user_id=user_id, milestone=milestone_type)
        return metrics

    # ------------------------------------------------------------------
    # Decay
    # ------------------------------------------------------------------

    def _apply_decay(self, metrics: RelationshipMetrics) -> RelationshipMetrics:
        """Apply inactivity decay based on time since last_seen."""
        metrics = metrics.model_copy(deep=True)
        now = utc(datetime.utcnow())
        days_inactive = (now - utc(metrics.last_seen)).total_seconds() / 86_400.0
        if days_inactive <= 0:
            return metrics

        for key, daily_rate in _DECAY_DAILY.items():
            floor = _DECAY_FLOOR[key]
            current = getattr(metrics, key)
            decayed = max(floor, current - daily_rate * days_inactive)
            # Only mutate if there is actual decay to avoid false negatives in tests
            if decayed < current:
                setattr(metrics, key, decayed)

        return metrics

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    async def _from_redis(self, user_id: str) -> RelationshipMetrics | None:
        if self._redis is None:
            return None
        key = f"persona:relationship:{user_id}"
        raw = await self._redis.get(key)
        if not raw:
            return None
        try:
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            return RelationshipMetrics(**data)
        except Exception as exc:
            logger.warning("relationship.redis_parse_failed", user_id=user_id, error=str(exc))
            return None

    async def _to_redis(self, user_id: str, metrics: RelationshipMetrics) -> None:
        if self._redis is None:
            return
        key = f"persona:relationship:{user_id}"
        payload = metrics.model_dump_json()
        await self._redis.set(key, payload, ex=86_400)

    async def _persist(self, metrics: RelationshipMetrics) -> None:
        """Upsert into PostgreSQL (asyncpg) or SQLite (SQLAlchemy)."""
        if self.state_store:
            await self.state_store.update(metrics.user_id, lambda emotion, _relationship: (emotion, metrics))
            return
        if self._db is None:
            self._memory_store[metrics.user_id] = metrics.model_copy(deep=True)
        # PostgreSQL path (asyncpg pool)
        if self._db:
            await self._db.execute(
                """
                INSERT INTO relationship_metrics (
                    user_id, intimacy, trust, familiarity, affection,
                    total_interactions, first_seen, last_seen
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (user_id) DO UPDATE SET
                    intimacy = EXCLUDED.intimacy,
                    trust = EXCLUDED.trust,
                    familiarity = EXCLUDED.familiarity,
                    affection = EXCLUDED.affection,
                    total_interactions = EXCLUDED.total_interactions,
                    last_seen = EXCLUDED.last_seen
                """,
                metrics.user_id,
                metrics.intimacy,
                metrics.trust,
                metrics.familiarity,
                metrics.affection,
                metrics.total_interactions,
                metrics.first_seen,
                metrics.last_seen,
            )
            return

        # SQLite path (SQLAlchemy async session)
        if self._sqlite_session_factory:
            await self._init_sqlite_schema()
            async with self._sqlite_session_factory() as session:
                await session.execute(
                    text(
                        """
                        INSERT OR REPLACE INTO relationship_metrics (
                            user_id, intimacy, trust, familiarity, affection,
                            total_interactions, first_seen, last_seen
                        ) VALUES (
                            :user_id, :intimacy, :trust, :familiarity, :affection,
                            :total_interactions, :first_seen, :last_seen
                        )
                        """
                    ),
                    {
                        "user_id": metrics.user_id,
                        "intimacy": metrics.intimacy,
                        "trust": metrics.trust,
                        "familiarity": metrics.familiarity,
                        "affection": metrics.affection,
                        "total_interactions": metrics.total_interactions,
                        "first_seen": metrics.first_seen,
                        "last_seen": metrics.last_seen,
                    },
                )
                await session.commit()

    # ------------------------------------------------------------------
    # SQLite schema init
    # ------------------------------------------------------------------

    async def _init_sqlite_schema(self) -> None:
        """Create relationship_metrics table for SQLite if not present."""
        if self._sqlite_schema_initialized or self._sqlite_session_factory is None:
            return
        async with self._sqlite_session_factory() as session:
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS relationship_metrics (
                        user_id TEXT PRIMARY KEY,
                        intimacy REAL NOT NULL DEFAULT 0.0,
                        trust REAL NOT NULL DEFAULT 0.0,
                        familiarity REAL NOT NULL DEFAULT 0.0,
                        affection REAL NOT NULL DEFAULT 0.0,
                        total_interactions INTEGER NOT NULL DEFAULT 0,
                        first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            await session.commit()
        self._sqlite_schema_initialized = True
        logger.info("relationship_tracker.sqlite_schema_initialized")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def apply_interaction(
    metrics,
    *,
    sentiment="neutral",
    has_disclosure=False,
    is_routine=False,
    shared_experience=False,
    hostile=False,
    now=None,
):
    """Bounded gains shrink near one; ordinary sadness never reduces trust."""
    metrics = metrics.model_copy(deep=True)
    metrics.total_interactions += 1
    metrics.last_seen = max(utc(metrics.last_seen), utc(now or datetime.utcnow()))
    gains = {
        "intimacy": (0.03 if has_disclosure else 0) + (0.02 if shared_experience else 0),
        "trust": 0.015 if sentiment == "positive" and not hostile else 0,
        "familiarity": 0.002 + (0.02 if is_routine else 0),
        "affection": 0.01 if sentiment == "positive" and not hostile else 0,
    }
    for key, gain in gains.items():
        current = getattr(metrics, key)
        setattr(metrics, key, _clamp(current + (1 - current) * gain))
    if hostile:
        metrics.trust = _clamp(metrics.trust - 0.0075)
    return metrics


def apply_milestone(metrics, milestone_type):
    metrics = metrics.model_copy(deep=True)
    metrics.last_seen = utc(datetime.utcnow())
    gains = {
        "first_voice_call": {"intimacy": 0.1, "trust": 0.05},
        "first_video_call": {"intimacy": 0.1, "trust": 0.05},
        "shared_secret": {"intimacy": 0.15, "trust": 0.1},
        "anniversary": {"affection": 0.1, "familiarity": 0.1},
    }.get(milestone_type, {"intimacy": 0.05, "affection": 0.05})
    for key, gain in gains.items():
        setattr(metrics, key, _clamp(getattr(metrics, key) + gain))
    return metrics


def _soft_cap(value: float, steepness: float = 5.0) -> float:
    """Diminishing returns as value approaches 1.0."""
    # logistic-like soft cap: gain slows above 0.7
    if value < 0.7:
        return value
    return 0.7 + (0.3 * (1 - (1 / (1 + steepness * (value - 0.7)))))
