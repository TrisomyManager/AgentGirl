"""Per-user conversational pacing preferences, independent of any host UI."""

import asyncio

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, String, Text

from shared_runtime.database import AsyncSessionLocal, Base


class ConversationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    natural_reply_enabled: bool = False
    acknowledgement_reply_probability: float = Field(default=0.35, ge=0, le=1)


class ConversationPreferencesORM(Base):
    __tablename__ = "persona_conversation_preferences"
    user_id = Column(String(128), primary_key=True)
    payload = Column(Text, nullable=False)


class ConversationPreferencesStore:
    def __init__(self, session_factory=AsyncSessionLocal):
        self.session_factory = session_factory
        self._ready = False
        self._initializing = asyncio.Lock()

    async def initialize(self):
        async with self._initializing:
            if self._ready:
                return
            async with self.session_factory() as session:
                connection = await session.connection()
                await connection.run_sync(
                    lambda conn: ConversationPreferencesORM.__table__.create(conn, checkfirst=True)
                )
                await session.commit()
            self._ready = True

    async def get(self, user_id: str) -> ConversationPreferences:
        await self.initialize()
        async with self.session_factory() as session:
            row = await session.get(ConversationPreferencesORM, user_id)
            return ConversationPreferences.model_validate_json(row.payload) if row else ConversationPreferences()

    async def save(self, user_id: str, preferences: ConversationPreferences) -> ConversationPreferences:
        await self.initialize()
        async with self.session_factory() as session:
            if session.bind.dialect.name == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            else:
                from sqlalchemy.dialects.postgresql import insert
            await session.execute(
                insert(ConversationPreferencesORM)
                .values(
                    user_id=user_id,
                    payload=preferences.model_dump_json(),
                )
                .on_conflict_do_update(index_elements=["user_id"], set_={"payload": preferences.model_dump_json()})
            )
            await session.commit()
        return preferences


conversation_preferences_store = ConversationPreferencesStore()
