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
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from shared.models import RelationshipMetrics

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

    def __init__(self, redis_client=None, db_pool=None, sqlite_session_factory=None):
        self._redis = redis_client
        self._db = db_pool  # asyncpg pool (PostgreSQL)
        self._sqlite_session_factory: Optional[Callable[[], AsyncSession]] = sqlite_session_factory
        self._sqlite_schema_initialized = False

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_metrics(self, user_id: str) -> RelationshipMetrics:
        """Return current metrics, preferring Redis cache."""
        cached = await self._from_redis(user_id)
        if cached:
            # Apply decay if stale
            cached = self._apply_decay(cached)
            return cached

        # PostgreSQL (asyncpg)
        if self._db:
            row = await self._db.fetchrow(
                "SELECT * FROM relationship_metrics WHERE user_id = $1", user_id
            )
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
    ) -> RelationshipMetrics:
        """Update metrics after a single interaction."""
        metrics = await self.get_metrics(user_id)
        metrics.total_interactions += 1
        metrics.last_seen = datetime.utcnow()

        if has_disclosure:
            metrics.intimacy = _clamp(metrics.intimacy + _INTIMACY_PER_DISCLOSURE)
            logger.debug("relationship.intimacy_up", user_id=user_id, reason="disclosure")

        if shared_experience:
            metrics.intimacy = _clamp(metrics.intimacy + _INTIMACY_PER_SHARED_EXPERIENCE)
            logger.debug("relationship.intimacy_up", user_id=user_id, reason="shared_experience")

        if sentiment == "positive":
            metrics.trust = _clamp(metrics.trust + _TRUST_PER_POSITIVE_INTERACTION)
            metrics.affection = _clamp(metrics.affection + _AFFECTION_PER_WARMTH_SIGNAL)
        elif sentiment == "negative":
            # Negative interactions hurt trust slightly, but can deepen intimacy
            # if handled with care (vulnerability)
            metrics.trust = _clamp(metrics.trust - _TRUST_PER_POSITIVE_INTERACTION * 0.5)

        if is_routine:
            metrics.familiarity = _clamp(metrics.familiarity + _FAMILIARITY_PER_ROUTINE)

        # Soft cap: as metrics approach 1.0, gains diminish
        metrics.intimacy = _soft_cap(metrics.intimacy)
        metrics.trust = _soft_cap(metrics.trust)
        metrics.familiarity = _soft_cap(metrics.familiarity)
        metrics.affection = _soft_cap(metrics.affection)

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
    ) -> RelationshipMetrics:
        """Apply a larger step change for relationship milestones."""
        metrics = await self.get_metrics(user_id)
        metrics.last_seen = datetime.utcnow()

        if milestone_type in ("first_voice_call", "first_video_call"):
            metrics.intimacy = _clamp(metrics.intimacy + 0.10)
            metrics.trust = _clamp(metrics.trust + 0.05)
        elif milestone_type == "shared_secret":
            metrics.intimacy = _clamp(metrics.intimacy + 0.15)
            metrics.trust = _clamp(metrics.trust + 0.10)
        elif milestone_type == "anniversary":
            metrics.affection = _clamp(metrics.affection + 0.10)
            metrics.familiarity = _clamp(metrics.familiarity + 0.10)
        else:
            metrics.intimacy = _clamp(metrics.intimacy + 0.05)
            metrics.affection = _clamp(metrics.affection + 0.05)

        await self._to_redis(user_id, metrics)
        await self._persist(metrics)
        logger.info("relationship.milestone", user_id=user_id, milestone=milestone_type)
        return metrics

    # ------------------------------------------------------------------
    # Decay
    # ------------------------------------------------------------------

    def _apply_decay(self, metrics: RelationshipMetrics) -> RelationshipMetrics:
        """Apply inactivity decay based on time since last_seen."""
        now = datetime.utcnow()
        days_inactive = (now - metrics.last_seen).total_seconds() / 86_400.0
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

    async def _from_redis(self, user_id: str) -> Optional[RelationshipMetrics]:
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


def _soft_cap(value: float, steepness: float = 5.0) -> float:
    """Diminishing returns as value approaches 1.0."""
    # logistic-like soft cap: gain slows above 0.7
    if value < 0.7:
        return value
    return 0.7 + (0.3 * (1 - (1 / (1 + steepness * (value - 0.7)))))
