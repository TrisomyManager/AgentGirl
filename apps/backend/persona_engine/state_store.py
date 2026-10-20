"""Durable persona state and atomic, replay-safe interaction updates.

SQL is authoritative in both Lite and PostgreSQL modes. Redis availability
cannot change a user's emotion or lose an acknowledged relationship update.
"""

import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, select

from shared_contracts.models import EmotionState, RelationshipMetrics
from shared_runtime.database import Base


class PersonaEmotionORM(Base):
    __tablename__ = "persona_emotions"
    user_id = Column(String(128), primary_key=True)
    payload = Column(Text, nullable=False)


class RelationshipMetricORM(Base):
    # Compatible with the historical relationship_metrics table.
    __tablename__ = "relationship_metrics"
    user_id = Column(String(128), primary_key=True)
    intimacy = Column(Float, nullable=False, default=0.0)
    trust = Column(Float, nullable=False, default=0.0)
    familiarity = Column(Float, nullable=False, default=0.0)
    affection = Column(Float, nullable=False, default=0.0)
    total_interactions = Column(Integer, nullable=False, default=0)
    first_seen = Column(DateTime(timezone=True), nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=False)


class PersonaEventORM(Base):
    __tablename__ = "persona_state_events"
    user_id = Column(String(128), primary_key=True)
    event_id = Column(String(200), primary_key=True)
    snapshot_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


def metrics_from_row(row):
    return RelationshipMetrics(**{key: getattr(row, key) for key in RelationshipMetrics.model_fields})


class PersonaStateStore:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self._ready = False
        self._initializing = asyncio.Lock()

    async def initialize(self):
        async with self._initializing:
            await self._initialize()

    async def _initialize(self):
        if self._ready:
            return
        # Lazy standalone SDK use must work without a host's startup lifecycle.
        async with self.session_factory() as session:
            connection = await session.connection()
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(
                    conn,
                    tables=[PersonaEmotionORM.__table__, RelationshipMetricORM.__table__, PersonaEventORM.__table__],
                )
            )
            await session.commit()
        self._ready = True

    async def get_emotion(self, user_id):
        await self.initialize()
        async with self.session_factory() as session:
            row = await session.get(PersonaEmotionORM, user_id)
            return EmotionState.model_validate_json(row.payload) if row else None

    async def get_relationship(self, user_id):
        await self.initialize()
        async with self.session_factory() as session:
            row = await session.get(RelationshipMetricORM, user_id)
            return metrics_from_row(row) if row else RelationshipMetrics(user_id=user_id)

    async def update(self, user_id, mutate, *, event_id=None):
        """Lock one user, apply a pure mutation, and persist both outputs once.

        The upsert also locks existing rows on SQLite; PostgreSQL uses a row
        lock. A concurrent duplicate observes the event after the first commit.
        """
        await self.initialize()
        async with self.session_factory() as session:
            if session.bind.dialect.name == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            else:
                from sqlalchemy.dialects.postgresql import insert
            now = datetime.now(UTC)
            await session.execute(
                insert(RelationshipMetricORM)
                .values(user_id=user_id, first_seen=now, last_seen=now)
                .on_conflict_do_nothing(index_elements=["user_id"])
            )
            relationship_row = (
                await session.execute(
                    select(RelationshipMetricORM).where(RelationshipMetricORM.user_id == user_id).with_for_update()
                )
            ).scalar_one()
            if event_id:
                previous = await session.get(PersonaEventORM, (user_id, event_id))
                if previous:
                    snapshot = json.loads(previous.snapshot_json)
                    return (
                        EmotionState(**snapshot["emotion"]) if snapshot["emotion"] else None,
                        RelationshipMetrics(**snapshot["relationship"]),
                    )
            emotion_row = await session.get(PersonaEmotionORM, user_id)
            emotion = EmotionState.model_validate_json(emotion_row.payload) if emotion_row else None
            emotion, relationship = mutate(emotion, metrics_from_row(relationship_row))
            if emotion is not None:
                if emotion_row is None:
                    session.add(PersonaEmotionORM(user_id=user_id, payload=emotion.model_dump_json()))
                else:
                    emotion_row.payload = emotion.model_dump_json()
            for key, value in relationship.model_dump().items():
                setattr(relationship_row, key, value)
            if event_id:
                snapshot = {
                    "emotion": emotion.model_dump(mode="json") if emotion else None,
                    "relationship": relationship.model_dump(mode="json"),
                }
                session.add(PersonaEventORM(user_id=user_id, event_id=event_id, snapshot_json=json.dumps(snapshot)))
            await session.commit()
            return emotion, relationship

    async def put_emotion(self, user_id, emotion):
        await self.update(user_id, lambda _emotion, relationship: (emotion, relationship))
