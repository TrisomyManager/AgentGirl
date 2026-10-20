"""Durable inbox and non-replaying delivery receipts for the single-process host."""

import hashlib
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import BigInteger, Column, String, Text, UniqueConstraint, func, select, update
from sqlalchemy.exc import IntegrityError

from shared_contracts import PlatformMessage
from shared_runtime.database import AsyncSessionLocal, Base


def now():
    return datetime.now(UTC).isoformat()


def digest(*values):
    import json

    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode("utf-8")).hexdigest()


class InboxORM(Base):
    __tablename__ = "platform_inbox"
    __table_args__ = (UniqueConstraint("message_key"),)
    id = Column(String(64), primary_key=True)
    message_key = Column(String(64), nullable=False)
    user_id = Column(String(128), nullable=False, index=True)
    binding_key = Column(String(64), nullable=False, index=True)
    account_key = Column(String(64), nullable=False)
    source_json = Column(Text, nullable=False)
    session_id = Column(String(36), nullable=False)
    status = Column(String(24), nullable=False, index=True)
    reply_text = Column(Text, nullable=True)
    sent_ids_json = Column(Text, nullable=False, default="[]")
    reason = Column(String(64), nullable=True)
    created_at = Column(String(64), nullable=False)
    updated_at = Column(String(64), nullable=False)


class CursorORM(Base):
    __tablename__ = "platform_cursors"
    account_key = Column(String(64), primary_key=True)
    position = Column(BigInteger, nullable=False)


class RevocationORM(Base):
    # Minimal hashes stop an old private host binding from recreating erased data.
    # Deliberately contains no user ID, actor, destination, credential or message.
    __tablename__ = "platform_binding_revocations"
    binding_key = Column(String(64), primary_key=True)
    created_at = Column(String(64), nullable=False)


class BindingORM(Base):
    __tablename__ = "platform_bindings"
    binding_key = Column(String(64), primary_key=True)
    user_id = Column(String(128), nullable=False, index=True)


class InboxFullError(RuntimeError):
    pass


class InboxStore:
    def __init__(self, sessions=AsyncSessionLocal):
        self.sessions = sessions

    async def revoked(self, key):
        async with self.sessions() as session:
            return await session.get(RevocationORM, key) is not None

    async def accept(self, message, account, binding, key):
        event_key = digest(account.identity_key(), message.event_id)
        message_key = digest(account.identity_key(), message.conversation_id, message.message_id)
        async with self.sessions() as session:
            if await session.get(RevocationORM, key):
                return "revoked"
            if await session.scalar(
                select(InboxORM.id).where((InboxORM.id == event_key) | (InboxORM.message_key == message_key))
            ):
                return "duplicate"
            # Bounded pending work; receivers must withhold acknowledgement when full.
            count = await session.scalar(
                select(func.count())
                .select_from(InboxORM)
                .where(
                    InboxORM.user_id == binding.user_id,
                    InboxORM.status.in_(["pending", "processing", "generated", "sending"]),
                )
            )
            if count >= 100:
                raise InboxFullError("Platform inbox is full")
            session.add(
                InboxORM(
                    id=event_key,
                    message_key=message_key,
                    user_id=binding.user_id,
                    binding_key=key,
                    account_key=account.identity_key(),
                    source_json=message.model_dump_json(),
                    session_id=str(uuid5(NAMESPACE_URL, "companion.platform.session:" + key)),
                    status="pending",
                    created_at=now(),
                    updated_at=now(),
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return "duplicate"
        return "accepted"

    async def recover(self):
        async with self.sessions() as session:
            # Model/tool execution and external sends may already have taken effect.
            for before, after in (("processing", "interrupted"), ("sending", "unknown")):
                await session.execute(
                    update(InboxORM)
                    .where(InboxORM.status == before)
                    .values(
                        status=after,
                        reason="host_restarted",
                        updated_at=now(),
                    )
                )
            await session.commit()

    async def register(self, account, binding):
        from .config import binding_fingerprint

        key = binding_fingerprint(account, binding)
        async with self.sessions() as session:
            if not await session.get(RevocationORM, key) and not await session.get(BindingORM, key):
                session.add(BindingORM(binding_key=key, user_id=binding.user_id))
                await session.commit()

    async def next(self):
        async with self.sessions() as session:
            return await session.scalar(
                select(InboxORM)
                .where(InboxORM.status.in_(["pending", "generated"]))
                .order_by(InboxORM.updated_at, InboxORM.id)
                .limit(1)
            )

    async def transition(self, identifier, before, after, **values):
        async with self.sessions() as session:
            result = await session.execute(
                update(InboxORM)
                .where(
                    InboxORM.id == identifier,
                    InboxORM.status == before,
                )
                .values(status=after, updated_at=now(), **values)
            )
            await session.commit()
            return bool(result.rowcount)

    async def cursor(self, key):
        async with self.sessions() as session:
            row = await session.get(CursorORM, key)
            return row.position if row else None

    async def advance(self, key, position):
        async with self.sessions() as session:
            row = await session.get(CursorORM, key)
            if row is None:
                session.add(CursorORM(account_key=key, position=position))
            elif position > row.position:
                row.position = position
            await session.commit()

    @staticmethod
    def message(row):
        return PlatformMessage.model_validate_json(row.source_json)


async def revoke_user_bindings(session, user_id, config):
    """Called inside the host's erasure transaction, after active work has settled."""
    from .config import binding_fingerprint

    keys = set((await session.scalars(select(InboxORM.binding_key).where(InboxORM.user_id == user_id))).all())
    keys.update((await session.scalars(select(BindingORM.binding_key).where(BindingORM.user_id == user_id))).all())
    for binding in config.bindings:
        if binding.user_id == user_id:
            keys.add(binding_fingerprint(config.account(binding.account_id), binding))
    for key in keys:
        if await session.get(RevocationORM, key) is None:
            session.add(RevocationORM(binding_key=key, created_at=now()))
    await session.flush()
