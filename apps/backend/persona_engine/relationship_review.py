"""Offline relationship review of host-supplied turns, with safe online reconciliation.

Old archives without observation receipts are described but never credited
again. New, explicitly versioned turns can repair a missed online transaction.
"""

import json
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String, Text, select

from persona_engine.emotion_engine import utc
from persona_engine.reaction import ReactionSignal, rule_reaction
from persona_engine.relationship_tracker import apply_interaction
from shared_runtime.database import Base


class RelationshipReviewORM(Base):
    __tablename__ = "persona_relationship_reviews"
    user_id = Column(String(128), primary_key=True)
    day = Column(String(10), primary_key=True)
    source_fingerprint = Column(String(64), nullable=False)
    summary_json = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class RelationshipReviewer:
    def __init__(self, state_store):
        self.store = state_store

    async def _initialize(self):
        await self.store.initialize()
        async with self.store._initializing:
            if getattr(self.store, "_reviews_ready", False):
                return
            async with self.store.session_factory() as session:
                connection = await session.connection()
                await connection.run_sync(lambda conn: RelationshipReviewORM.__table__.create(conn, checkfirst=True))
                await session.commit()
            self.store._reviews_ready = True

    async def review(self, user_id, day, turns, fingerprint):
        await self._initialize()
        async with self.store.session_factory() as session:
            previous = await session.get(RelationshipReviewORM, (user_id, day))
            if previous and previous.source_fingerprint == fingerprint:
                return json.loads(previous.summary_json) | {"status": "unchanged"}
        sentiments = Counter()
        eligible, ignored, signals = 0, 0, Counter()
        for turn in turns:
            metadata = turn.get("metadata") or {}
            if metadata.get("user_id") not in {None, user_id}:
                continue
            message = str(turn.get("user_message") or "").strip()
            if not message:
                continue
            try:
                reaction = (
                    ReactionSignal(**metadata["reaction"]) if metadata.get("reaction") else rule_reaction(message)
                )
                timestamp = utc(datetime.fromisoformat(turn["timestamp"]))
            except (ValueError, TypeError, KeyError):
                reaction = rule_reaction(message)
                timestamp = None
            sentiments[reaction.sentiment] += 1
            for key in ("has_disclosure", "is_routine", "shared_experience"):
                signals[key] += int(getattr(reaction, key))
            if metadata.get("persona_observation_version") != 1 or not turn.get("turn_id") or timestamp is None:
                ignored += 1
                continue
            eligible += 1

            def reconcile(emotion, relationship, reaction=reaction, timestamp=timestamp):
                # A historical review does not alter today's emotion or activity.
                if relationship.total_interactions == 0:
                    relationship.first_seen = timestamp
                    relationship.last_seen = timestamp
                return emotion, apply_interaction(
                    relationship,
                    sentiment=reaction.sentiment,
                    has_disclosure=reaction.has_disclosure,
                    is_routine=reaction.is_routine,
                    shared_experience=reaction.shared_experience,
                    hostile=reaction.hostile,
                    now=timestamp,
                )

            await self.store.update(user_id, reconcile, event_id=f"turn:{turn['turn_id']}")
        summary = {
            "user_id": user_id,
            "day": day,
            "turn_count": sum(sentiments.values()),
            "sentiment_counts": dict(sentiments),
            "signals": dict(signals),
            "observed_turns": eligible,
            "legacy_turns_not_recredited": ignored,
        }
        async with self.store.session_factory() as session:
            if session.bind.dialect.name == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            else:
                from sqlalchemy.dialects.postgresql import insert
            values = {
                "user_id": user_id,
                "day": day,
                "source_fingerprint": fingerprint,
                "summary_json": json.dumps(summary),
                "updated_at": datetime.now(UTC),
            }
            await session.execute(
                insert(RelationshipReviewORM)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["user_id", "day"],
                    set_=values,
                )
            )
            await session.commit()
        return summary | {"status": "updated"}

    async def list_reviews(self, user_id, limit=7):
        await self._initialize()
        async with self.store.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(RelationshipReviewORM)
                        .where(RelationshipReviewORM.user_id == user_id)
                        .order_by(RelationshipReviewORM.day.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return [json.loads(row.summary_json) | {"updated_at": utc(row.updated_at).isoformat()} for row in rows]
