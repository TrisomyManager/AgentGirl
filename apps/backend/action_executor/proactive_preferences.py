"""Per-user care preferences and activity, persisted independently of the host UI."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Column, String, Text, select

from shared_runtime.config import get_settings
from shared_runtime.database import AsyncSessionLocal, Base


class CarePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    idle_checkin: bool = True
    morning_greeting: bool = True
    evening_greeting: bool = True
    memory_followup: bool = True
    timezone: str = "Asia/Shanghai"
    dnd_start_hour: int = Field(default=22, ge=0, le=23)
    dnd_end_hour: int = Field(default=7, ge=0, le=23)
    cooldown_minutes: int = Field(default=120, ge=1, le=10080)
    max_per_day: int = Field(default=3, ge=0, le=20)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("请选择有效的 IANA 时区，例如 Asia/Shanghai") from exc
        return value


class CareUserORM(Base):
    __tablename__ = "care_users"
    user_id = Column(String(128), primary_key=True)
    preferences_json = Column(Text, nullable=False, default="{}")
    last_seen = Column(String(64), nullable=True)
    session_id = Column(String(128), nullable=True)


def default_preferences() -> CarePreferences:
    settings = get_settings()
    return CarePreferences(
        enabled=settings.proactive_enabled,
        morning_greeting=settings.proactive_morning_greeting_enabled,
        evening_greeting=settings.proactive_evening_greeting_enabled,
        memory_followup=settings.proactive_memory_followup_enabled,
        dnd_start_hour=settings.proactive_dnd_start_hour,
        dnd_end_hour=settings.proactive_dnd_end_hour,
        cooldown_minutes=settings.proactive_cooldown_minutes,
        max_per_day=settings.proactive_max_per_day,
    )


class CarePreferencesStore:
    def __init__(self, session_factory=None) -> None:
        self.sessions = session_factory or AsyncSessionLocal

    async def get(self, user_id: str) -> CarePreferences:
        async with self.sessions() as session:
            row = await session.get(CareUserORM, user_id)
            overrides = json.loads(row.preferences_json) if row else {}
        return CarePreferences.model_validate(default_preferences().model_dump() | overrides)

    async def save(self, user_id: str, preferences: CarePreferences) -> CarePreferences:
        async with self.sessions() as session:
            await self._upsert(session, user_id, preferences_json=preferences.model_dump_json())
            await session.commit()
        return preferences

    async def touch(self, user_id: str, session_id: str | None = None) -> None:
        async with self.sessions() as session:
            values = {"last_seen": datetime.now(UTC).isoformat()}
            if session_id:
                values["session_id"] = session_id
            await self._upsert(session, user_id, **values)
            await session.commit()

    @staticmethod
    async def _upsert(session, user_id: str, **values) -> None:
        if session.bind.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            from sqlalchemy.dialects.postgresql import insert
        statement = insert(CareUserORM).values(user_id=user_id, **values)
        await session.execute(statement.on_conflict_do_update(index_elements=["user_id"], set_=values))

    async def activity(self, user_id: str) -> tuple[datetime | None, str | None]:
        async with self.sessions() as session:
            row = await session.get(CareUserORM, user_id)
            if row is None:
                return None, None
            return (datetime.fromisoformat(row.last_seen) if row.last_seen else None, row.session_id)

    async def users(self) -> list[str]:
        async with self.sessions() as session:
            return list((await session.execute(select(CareUserORM.user_id))).scalars().all())


care_preferences_store = CarePreferencesStore()
