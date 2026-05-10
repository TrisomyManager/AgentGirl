"""user_profile P1-B 单元测试 (内存实现 + SQLite 实现)."""

from __future__ import annotations

import logging
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from user_profile import (
    InMemoryUserProfileStore,
    UserProfileSnapshot,
)


@pytest.mark.asyncio
async def test_inmemory_upsert_and_get() -> None:
    store = InMemoryUserProfileStore()
    snap = UserProfileSnapshot(
        user_id="u1",
        display_name="阿正",
        locale="zh-CN",
        preferences={"role_id": "default"},
    )
    await store.upsert(snap)
    got = await store.get("u1")
    assert got is not None
    assert got.display_name == "阿正"
    assert got.preferences["role_id"] == "default"


@pytest.mark.asyncio
async def test_inmemory_merge_preferences_creates_when_missing() -> None:
    store = InMemoryUserProfileStore()
    snap = await store.merge_preferences("u2", theme="dark")
    assert snap.user_id == "u2"
    assert snap.preferences["theme"] == "dark"


@pytest.mark.asyncio
async def test_inmemory_merge_preferences_updates_existing() -> None:
    store = InMemoryUserProfileStore()
    await store.upsert(
        UserProfileSnapshot(user_id="u3", preferences={"theme": "light"})
    )
    snap = await store.merge_preferences("u3", theme="dark", lang="en-US")
    assert snap.preferences == {"theme": "dark", "lang": "en-US"}


@pytest.mark.asyncio
async def test_get_returns_none_for_missing() -> None:
    store = InMemoryUserProfileStore()
    assert await store.get("nope") is None


# ---------------------------------------------------------------------------
# 回归: get_default_store SQLite 保底
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_default_store_returns_sqlite_not_memory() -> None:
    """SQLiteUserProfileStore() 后再 get_default_store() 必须返回 SQLite 实例."""
    import user_profile
    from user_profile import SQLiteUserProfileStore, get_default_store

    try:
        _ = SQLiteUserProfileStore()
    except Exception:
        pytest.skip("shared.database not available in this environment")

    user_profile._default_store = None
    store = get_default_store()
    assert isinstance(store, SQLiteUserProfileStore), (
        f"Expected SQLiteUserProfileStore, got {type(store).__name__}"
    )


# ---------------------------------------------------------------------------
# 回归: invalid role_id → 陪伴者 兜底 + EmotionState 无 warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_role_id_fallback_to_default_persona_no_warn(caplog: pytest.LogCaptureFixture) -> None:
    """给定 invalid role_id, _recall_memory_monolithic 必须 fallback 到 "陪伴者",
    persona_engine.runtime / persona_engine.persona_store 的 logger 不产生 warning."""
    from core_orchestrator.state_machine import _recall_memory_monolithic
    from persona_engine.emotion_engine import EmotionEngine
    from persona_engine.relationship_tracker import RelationshipTracker
    from shared_contracts.models import Platform, TurnContext, UserProfile

    user = UserProfile(
        user_id="test_invalid_role",
        display_name="TestUser",
        platform=Platform.APP,
        language="zh-CN",
    )
    tc = TurnContext(
        turn_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user=user,
        user_message="你好",
        platform=Platform.APP,
        has_voice=False,
    )
    state: dict = {"turn_context": tc}

    # Inject in-memory user_profile with invalid role_id
    import user_profile
    mock_store = InMemoryUserProfileStore()
    await mock_store.upsert(
        UserProfileSnapshot(
            user_id="test_invalid_role",
            preferences={"role_id": "nonexistent_role_id"},
        )
    )
    user_profile._default_store = mock_store

    # Inject no-redis engines via runtime setters
    from persona_engine.runtime import (
        set_emotion_engine,
        set_relationship_tracker,
    )
    set_emotion_engine(EmotionEngine(redis_client=None))
    set_relationship_tracker(RelationshipTracker(redis_client=None, db_pool=None))

    # Mock memory_client
    mock_resp = MagicMock()
    mock_resp.json.return_value = None

    import structlog

    # Capture persona_engine logs at WARNING level
    caplog.set_level(logging.WARNING, logger="persona_engine.runtime")
    caplog.set_level(logging.WARNING, logger="persona_engine.persona_store")

    with patch("core_orchestrator.state_machine._is_monolithic", return_value=True), patch(
        "core_orchestrator.state_machine.memory_client.post",
        new_callable=AsyncMock,
    ) as mock_post:
            mock_post.return_value = mock_resp
            mock_log = structlog.get_logger()
            result_state = await _recall_memory_monolithic(tc, state, mock_log)

    persona = result_state.get("persona_profile")
    assert persona is not None
    assert persona.name == "陪伴者", (
        f"Expected '陪伴者' fallback, got {persona.name!r}"
    )

    warn_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warn_records) == 0, (
        f"Expected 0 warnings from persona_engine, got {len(warn_records)}: "
        f"{[r.message for r in warn_records]}"
    )

    # Cleanup: restore module-level state to avoid leaking across tests
    user_profile._default_store = None
    import persona_engine.runtime as _runtime
    _runtime._emotion_engine = None  # type: ignore[attr-defined]
    _runtime._relationship_tracker = None  # type: ignore[attr-defined]
