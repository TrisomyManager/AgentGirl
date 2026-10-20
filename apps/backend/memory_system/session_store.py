"""Durable conversation history for SQLite and PostgreSQL; context caches remain replaceable."""

import json
from datetime import UTC, datetime

from sqlalchemy import Column, Integer, String, Text, UniqueConstraint, delete, select, update

from shared_runtime.database import AsyncSessionLocal, Base, engine
from shared_runtime.lite_mode import InMemoryShortTermMemory


def _insert(session, model):
    if session.bind.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        from sqlalchemy.dialects.postgresql import insert
    return insert(model)


class ConversationTurnORM(Base):
    __tablename__ = "conversation_turns"
    __table_args__ = (UniqueConstraint("session_id", "turn_id"),)

    seq = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(128), nullable=False, index=True)
    turn_id = Column(String(128), nullable=False)
    user_id = Column(String(128), nullable=True, index=True)
    payload_json = Column(Text, nullable=False)


class SessionDigestORM(Base):
    __tablename__ = "session_digests"
    session_id = Column(String(128), primary_key=True)
    payload_json = Column(Text, nullable=False)


class SessionOwnerORM(Base):
    __tablename__ = "conversation_session_owners"
    session_id = Column(String(128), primary_key=True)
    user_id = Column(String(128), nullable=False, index=True)


class PersistentSessionMemory(InMemoryShortTermMemory):
    """Persist turns; keep transient user context in the existing in-memory cache."""

    def __init__(self, max_entries=100, default_ttl=3600):
        super().__init__(max_entries=max_entries, default_ttl=default_ttl)
        self._schema_ready = False

    async def _ensure_schema(self):
        if not self._schema_ready:
            async with engine.begin() as connection:
                await connection.run_sync(ConversationTurnORM.__table__.create, checkfirst=True)
                await connection.run_sync(SessionDigestORM.__table__.create, checkfirst=True)
                await connection.run_sync(SessionOwnerORM.__table__.create, checkfirst=True)
            self._schema_ready = True

    async def authorize_session(self, session_id: str, user_id: str, *, claim=False):
        """Bind new sessions atomically and refuse foreign or unowned legacy history."""
        if not isinstance(session_id, str) or not 1 <= len(session_id) <= 128:
            raise PermissionError("Invalid session")
        await self._ensure_schema()
        async with AsyncSessionLocal() as session:
            owners = set((await session.execute(select(ConversationTurnORM.user_id).where(
                ConversationTurnORM.session_id == session_id,
            ).distinct())).scalars())
            if owners - {user_id}:
                raise PermissionError("Foreign session")
            owner = await session.get(SessionOwnerORM, session_id)
            if owner is None and not owners and await session.get(SessionDigestORM, session_id) is not None:
                raise PermissionError("Unowned legacy archive")
            if owner is None and (claim or owners):
                await session.execute(_insert(session, SessionOwnerORM).values(
                    session_id=session_id, user_id=user_id,
                ).on_conflict_do_nothing())
                owner = await session.get(SessionOwnerORM, session_id)
            if owner and owner.user_id != user_id:
                raise PermissionError("Foreign session")
            await session.commit()
            return owner is not None

    async def add_turn(self, session_id, turn_id, user_message, assistant_message, emotion=None, metadata=None):
        await self._ensure_schema()
        metadata = metadata or {}
        payload = {
            "session_id": session_id,
            "turn_id": turn_id,
            "user_message": user_message,
            "assistant_message": assistant_message,
            "emotion": getattr(emotion, "value", emotion),
            "metadata": metadata,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        async with AsyncSessionLocal() as session:
            statement = (
                _insert(session, ConversationTurnORM)
                .values(
                    session_id=session_id,
                    turn_id=turn_id,
                    user_id=metadata.get("user_id"),
                    payload_json=json.dumps(payload, ensure_ascii=False, default=str),
                )
                .on_conflict_do_nothing(index_elements=["session_id", "turn_id"])
            )
            await session.execute(statement)
            await session.commit()

    async def get_session_turns(self, session_id):
        await self._ensure_schema()
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(ConversationTurnORM.seq, ConversationTurnORM.payload_json)
                    .where(ConversationTurnORM.session_id == session_id)
                    .order_by(ConversationTurnORM.seq.desc())
                    .limit(self.max_entries)
                )
            ).all()
        return [json.loads(row.payload_json) | {"storage_seq": row.seq} for row in reversed(rows)]

    async def load_digest(self, session_id):
        await self._ensure_schema()
        async with AsyncSessionLocal() as session:
            row = await session.get(SessionDigestORM, session_id)
            return json.loads(row.payload_json) if row else {}

    async def save_digest(self, session_id, digest):
        await self._ensure_schema()
        payload = json.dumps(digest, ensure_ascii=False)
        async with AsyncSessionLocal() as session:
            source = update(ConversationTurnORM).where(ConversationTurnORM.session_id == session_id)
            if digest.get("covered_turn_id"):
                source = source.where(ConversationTurnORM.turn_id == digest["covered_turn_id"])
            locked = await session.execute(source.values(payload_json=ConversationTurnORM.payload_json))
            if not locked.rowcount:
                return
            await session.execute(
                _insert(session, SessionDigestORM)
                .values(
                    session_id=session_id,
                    payload_json=payload,
                )
                .on_conflict_do_update(index_elements=["session_id"], set_={"payload_json": payload})
            )
            await session.commit()

    async def users(self):
        await self._ensure_schema()
        async with AsyncSessionLocal() as session:
            return list(
                (
                    await session.execute(
                        select(ConversationTurnORM.user_id)
                        .where(
                            ConversationTurnORM.user_id.is_not(None),
                        )
                        .distinct()
                    )
                )
                .scalars()
                .all()
            )

    async def user_turns(self, user_id, *, start=None, end=None):
        await self._ensure_schema()
        turns = []
        async with AsyncSessionLocal() as session:
            result = await session.stream(
                select(ConversationTurnORM.payload_json)
                .where(
                    ConversationTurnORM.user_id == user_id,
                )
                .order_by(ConversationTurnORM.seq)
            )
            async for row in result:
                payload = json.loads(row.payload_json)
                timestamp = datetime.fromisoformat(payload["timestamp"])
                timestamp = timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp.astimezone(UTC)
                if (start is None or timestamp >= start) and (end is None or timestamp < end):
                    turns.append(payload)
        return turns

    async def latest_user_digest(self, user_id, *, exclude_session_id=None):
        await self._ensure_schema()
        async with AsyncSessionLocal() as session:
            statement = (
                select(SessionDigestORM.payload_json)
                .join(
                    ConversationTurnORM,
                    ConversationTurnORM.session_id == SessionDigestORM.session_id,
                )
                .where(ConversationTurnORM.user_id == user_id)
            )
            if exclude_session_id:
                statement = statement.where(SessionDigestORM.session_id != exclude_session_id)
            raw = (
                await session.execute(statement.order_by(ConversationTurnORM.seq.desc()).limit(1))
            ).scalar_one_or_none()
            return json.loads(raw) if raw else {}

    async def get_recent_context(self, session_id, last_n=5):
        turns = await self.get_session_turns(session_id)
        return "\n".join(
            f"User: {turn['user_message']}\nAssistant: {turn['assistant_message']}" for turn in turns[-last_n:]
        )

    async def clear_session(self, session_id):
        await self._ensure_schema()
        async with AsyncSessionLocal() as session:
            await session.execute(delete(ConversationTurnORM).where(ConversationTurnORM.session_id == session_id))
            await session.execute(delete(SessionDigestORM).where(SessionDigestORM.session_id == session_id))
            await session.commit()

    async def clear_user(self, user_id, *, session=None):
        await self._ensure_schema()
        if session is None:
            async with AsyncSessionLocal() as own_session:
                cleared = await self.clear_user(user_id, session=own_session)
                await own_session.commit()
                return cleared
        else:
            session_ids = list(
                (
                    await session.execute(
                        select(ConversationTurnORM.session_id)
                        .where(
                            ConversationTurnORM.user_id == user_id,
                        )
                        .distinct()
                    )
                )
                .scalars()
                .all()
            )
            await session.execute(delete(ConversationTurnORM).where(ConversationTurnORM.user_id == user_id))
            cleared = []
            for session_id in session_ids:
                remaining = (
                    await session.execute(
                        select(ConversationTurnORM.seq)
                        .where(
                            ConversationTurnORM.session_id == session_id,
                        )
                        .limit(1)
                    )
                ).first()
                if remaining is None:
                    await session.execute(delete(SessionDigestORM).where(SessionDigestORM.session_id == session_id))
                    cleared.append(session_id)
        return cleared
