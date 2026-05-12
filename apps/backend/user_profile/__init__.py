"""user_profile —— 跨对话用户画像 (P1-B 可用实现).

设计目标:
- 维护用户的偏好 / 性格 / 兴趣 / 关键事件等长期画像
- 与 memory_system 分工: memory 侧重事件/关系图, user_profile 侧重稳定属性
- 业务侧通过 ``UserProfileStore`` 读写, 第三方宿主可替换底层存储

P1-B 升级要点:
- 新增 ``SQLiteUserProfileStore`` —— 复用 ``shared.database`` 引擎 (Lite 模式 SQLite, 生产 PG)
- 新增 ``get_default_store()`` —— 进程级单例, orchestrator 主链路调用
- ORM 模型 ``UserProfileORM`` 注册到 ``shared.database.Base``, 自动随 init_database_schema 建表
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol

__all__ = [
    "UserProfileSnapshot",
    "UserProfileStore",
    "InMemoryUserProfileStore",
    "SQLiteUserProfileStore",
    "get_default_store",
]


@dataclass
class UserProfileSnapshot:
    user_id: str
    display_name: Optional[str] = None
    locale: str = "zh-CN"
    preferences: Dict[str, Any] = field(default_factory=dict)
    traits: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class UserProfileStore(Protocol):
    async def get(self, user_id: str) -> Optional[UserProfileSnapshot]: ...
    async def upsert(self, snapshot: UserProfileSnapshot) -> None: ...
    async def merge_preferences(self, user_id: str, **prefs: Any) -> UserProfileSnapshot: ...


class InMemoryUserProfileStore:
    """进程级内存实现, 用于 Demo / 单测."""

    def __init__(self) -> None:
        self._store: Dict[str, UserProfileSnapshot] = {}

    async def get(self, user_id: str) -> Optional[UserProfileSnapshot]:
        return self._store.get(user_id)

    async def upsert(self, snapshot: UserProfileSnapshot) -> None:
        self._store[snapshot.user_id] = snapshot

    async def merge_preferences(self, user_id: str, **prefs: Any) -> UserProfileSnapshot:
        snap = self._store.get(user_id) or UserProfileSnapshot(user_id=user_id)
        snap.preferences.update(prefs)
        self._store[user_id] = snap
        return snap


# ---------------------------------------------------------------------------
# SQLite (shared.database) backed store
# ---------------------------------------------------------------------------


_UserProfileORM: Any = None


def _get_orm():
    """Return the module-level singleton ORM class.

    Only builds the class once — calling ``_build_orm()`` a second time
    would re-define ``__tablename__ = "user_profiles"`` on the same
    ``Base.metadata``, which SQLAlchemy rejects with ``InvalidRequestError``.
    """
    global _UserProfileORM
    if _UserProfileORM is None:
        _UserProfileORM = _build_orm()
    return _UserProfileORM


def _build_orm():
    """Build the SQLAlchemy ORM model for ``user_profiles`` table.

    Must only be called once per process — use ``_get_orm()`` instead.
    """
    from sqlalchemy import Column, DateTime, String, Text, func

    from shared.database import Base

    class UserProfileORM(Base):  # type: ignore[misc, valid-type]
        __tablename__ = "user_profiles"

        user_id = Column(String(128), primary_key=True)
        display_name = Column(String(128), nullable=True)
        locale = Column(String(16), nullable=False, default="zh-CN")
        preferences_json = Column(Text, nullable=False, default="{}")
        traits_json = Column(Text, nullable=False, default="{}")
        metadata_json = Column(Text, nullable=False, default="{}")
        created_at = Column(DateTime(timezone=True), server_default=func.now())
        updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    return UserProfileORM


class SQLiteUserProfileStore:
    """基于 ``shared.database`` 的持久化实现 (Lite 模式 SQLite, 生产 PG).

    通过 ``shared.database.init_database_schema()`` 自动建表 — 模块只需在
    被 import 时把 ORM 注册进 ``Base.metadata``.
    """

    def __init__(self) -> None:
        self._orm = _get_orm()

    @staticmethod
    def _to_snapshot(row: Any) -> UserProfileSnapshot:
        return UserProfileSnapshot(
            user_id=row.user_id,
            display_name=row.display_name,
            locale=row.locale or "zh-CN",
            preferences=json.loads(row.preferences_json or "{}"),
            traits=json.loads(row.traits_json or "{}"),
            metadata=json.loads(row.metadata_json or "{}"),
        )

    async def get(self, user_id: str) -> Optional[UserProfileSnapshot]:
        from shared.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            row = await session.get(self._orm, user_id)
            if row is None:
                return None
            return self._to_snapshot(row)

    async def upsert(self, snapshot: UserProfileSnapshot) -> None:
        from shared.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            row = await session.get(self._orm, snapshot.user_id)
            if row is None:
                row = self._orm(user_id=snapshot.user_id)
                session.add(row)
            row.display_name = snapshot.display_name
            row.locale = snapshot.locale or "zh-CN"
            row.preferences_json = json.dumps(snapshot.preferences or {}, ensure_ascii=False)
            row.traits_json = json.dumps(snapshot.traits or {}, ensure_ascii=False)
            row.metadata_json = json.dumps(snapshot.metadata or {}, ensure_ascii=False)
            await session.commit()

    async def merge_preferences(self, user_id: str, **prefs: Any) -> UserProfileSnapshot:
        from shared.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            row = await session.get(self._orm, user_id)
            if row is None:
                row = self._orm(
                    user_id=user_id,
                    locale="zh-CN",
                    preferences_json="{}",
                    traits_json="{}",
                    metadata_json="{}",
                )
                session.add(row)
                await session.flush()
            current = json.loads(row.preferences_json or "{}")
            current.update(prefs)
            row.preferences_json = json.dumps(current, ensure_ascii=False)
            await session.commit()
            await session.refresh(row)
            return self._to_snapshot(row)


# ---------------------------------------------------------------------------
# Default store (process-level singleton)
# ---------------------------------------------------------------------------

_default_store: Optional[UserProfileStore] = None


def get_default_store() -> UserProfileStore:
    """Return process-level default store.

    Selects ``SQLiteUserProfileStore`` when ``shared.database`` is available;
    falls back to ``InMemoryUserProfileStore`` for pure-Python environments
    (e.g. third-party hosts without sqlalchemy).
    """
    global _default_store
    if _default_store is None:
        try:
            _default_store = SQLiteUserProfileStore()
        except Exception:
            _default_store = InMemoryUserProfileStore()
    return _default_store
