"""Tests for action_executor: registry, handlers, reminders store, scheduler.

Covers the outer contract — ``ActionRegistry.dispatch`` can find a
keyword-matched handler, built-in handlers return well-shaped
``ActionResult`` objects, the SQLite reminders store can insert /
list / mark fired / cancel, and the scheduler tick fires due reminders
into the ProactivePushBus.

Lite mode is required so the SQLite engine is in play (the suite-wide
conftest already sets ``COMPANION_LITE_MODE=true`` before any imports).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("COMPANION_LITE_MODE", "true")

from action_executor import handlers as _builtins_module  # noqa: F401 — register builtins
from action_executor.handlers import (
    cancel_reminder,
    get_time,
    get_weather,
    list_reminders,
    set_reminder,
)
from action_executor.push_bus import ProactivePushBus, PushEvent
from action_executor.registry import ActionRegistry, ActionResult, get_registry
from action_executor.reminders import (
    ReminderScheduler,
    RemindersStore,
    extract_reminder_body,
    parse_relative_delay,
    parse_repeat_interval,
)
from shared.database import init_database_schema


@pytest.fixture(autouse=True, scope="module")
async def _ensure_schema() -> None:
    await init_database_schema()


# ---------------------------------------------------------------------------
# Registry & metadata
# ---------------------------------------------------------------------------


def test_builtins_are_registered() -> None:
    registry = get_registry()
    names = {a["name"] for a in registry.list_actions()}
    assert {"get_time", "get_weather", "set_reminder", "list_reminders", "cancel_reminder"} <= names


def test_find_by_keyword_routes_correctly() -> None:
    registry = get_registry()
    assert registry.find_by_keyword("现在几点了") == "get_time"
    assert registry.find_by_keyword("今天天气怎么样") == "get_weather"
    assert registry.find_by_keyword("提醒我下午开会") == "set_reminder"
    assert registry.find_by_keyword("我有什么提醒") == "list_reminders"
    assert registry.find_by_keyword("一个普通的聊天消息") is None


@pytest.mark.asyncio
async def test_dispatch_unknown_returns_clear_error() -> None:
    registry = ActionRegistry()  # private registry to test without builtins
    result = await registry.dispatch("nope", {})
    assert result.ok is False
    assert "未注册" in result.message


@pytest.mark.asyncio
async def test_register_decorator_rejects_sync_handler() -> None:
    registry = ActionRegistry()

    def sync_handler(_p):  # noqa: ANN001 — intentional bad shape
        return ActionResult()

    with pytest.raises(TypeError):
        registry.register("bad", "bad")(sync_handler)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Built-in handlers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_time_returns_formatted_now() -> None:
    result = await get_time({})
    assert result.ok
    assert "现在是" in result.message
    assert "星期" in result.message
    assert "timestamp" in result.data


@pytest.mark.asyncio
async def test_get_weather_uses_open_meteo(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_fetch(_loc: str):
        return True, "「测试市」现在晴朗", {"source": "open_meteo", "resolved_name": "测试市"}

    monkeypatch.setattr(
        "action_executor.weather_open_meteo.fetch_current_weather",
        _fake_fetch,
    )
    result = await get_weather({"location": "测试市"})
    assert result.ok
    assert "测试市" in result.message
    assert result.data.get("source") == "open_meteo"


@pytest.mark.asyncio
async def test_set_reminder_with_relative_delay_creates_row() -> None:
    result = await set_reminder(
        {
            "user_id": "test-user",
            "raw_text": "3 分钟后提醒我喝水",
        }
    )
    assert result.ok, result.message
    assert "3 分钟后" in result.message or "180 秒后" in result.message
    reminder = result.data["reminder"]
    assert reminder["text"] == "喝水"
    assert reminder["status"] == "pending"


@pytest.mark.asyncio
async def test_set_reminder_rejects_when_no_delay() -> None:
    result = await set_reminder({"user_id": "test-user", "raw_text": "提醒我吃饭"})
    assert result.ok is False
    assert "什么时候" in result.message


@pytest.mark.asyncio
async def test_set_reminder_rejects_when_no_body() -> None:
    result = await set_reminder({"user_id": "test-user", "raw_text": "5 分钟后"})
    assert result.ok is False
    assert result.data["error"] == "empty_body"


@pytest.mark.asyncio
async def test_list_then_cancel_reminder_round_trip() -> None:
    user_id = "round-trip-user"
    create = await set_reminder(
        {"user_id": user_id, "raw_text": "10 分钟后提醒我开会"}
    )
    assert create.ok, create.message
    rid = create.data["reminder"]["id"]

    listing = await list_reminders({"user_id": user_id})
    assert listing.ok
    assert any(r["id"] == rid for r in listing.data["reminders"])

    cancelled = await cancel_reminder({"user_id": user_id, "id": rid})
    assert cancelled.ok
    assert cancelled.data["cancelled"] is True

    # Listing again should not include the cancelled reminder.
    listing2 = await list_reminders({"user_id": user_id})
    assert all(r["id"] != rid for r in listing2.data["reminders"])


# ---------------------------------------------------------------------------
# Reminders store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reminders_store_due_filter() -> None:
    store = RemindersStore()
    now = datetime.now(timezone.utc)

    past = await store.add(
        user_id="due-user",
        text="过去的提醒",
        fire_at=now - timedelta(seconds=5),
    )
    future = await store.add(
        user_id="due-user",
        text="将来的提醒",
        fire_at=now + timedelta(minutes=30),
    )

    due = await store.list_due()
    due_ids = {r.id for r in due}
    assert past.id in due_ids
    assert future.id not in due_ids


@pytest.mark.asyncio
async def test_reminders_store_mark_fired_is_idempotent() -> None:
    store = RemindersStore()
    r = await store.add(
        user_id="fire-user",
        text="抢咖啡",
        fire_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    first = await store.mark_fired(r.id)
    second = await store.mark_fired(r.id)
    assert first is True
    assert second is False  # already fired, second time is a no-op


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_tick_fires_due_reminders_into_push_bus() -> None:
    store = RemindersStore()
    user_id = "sched-user"

    fire_now = await store.add(
        user_id=user_id,
        text="测试事件",
        fire_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    scheduler = ReminderScheduler(poll_interval=999)  # we drive _tick_once manually
    received_events: list[dict] = []
    seen_target = asyncio.Event()

    async def _consume(bus: ProactivePushBus) -> None:
        async for event in bus.subscribe():
            received_events.append({"kind": event.kind, "payload": event.payload})
            if event.kind == "reminder_fired" and event.payload.get("id") == fire_now.id:
                seen_target.set()
                return

    consumer = asyncio.create_task(_consume(scheduler._bus))  # noqa: SLF001
    await asyncio.sleep(0.05)  # let the subscriber register

    fired = await scheduler._tick_once()  # noqa: SLF001
    assert fired >= 1

    try:
        await asyncio.wait_for(seen_target.wait(), timeout=2)
    finally:
        consumer.cancel()

    payloads = [e["payload"] for e in received_events if e["kind"] == "reminder_fired"]
    assert any(p.get("id") == fire_now.id for p in payloads), (
        f"target reminder not in fired events; saw: {payloads}"
    )


# ---------------------------------------------------------------------------
# Push bus polling (SSE fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_bus_poll_since_returns_incrementing_events() -> None:
    bus = ProactivePushBus()
    await bus.publish(PushEvent(kind="ping_test", payload={"x": 1}))
    first = await bus.poll_since(0)
    assert first["latest_seq"] == 1
    assert len(first["events"]) == 1
    assert first["events"][0]["kind"] == "ping_test"

    empty = await bus.poll_since(first["latest_seq"])
    assert empty["events"] == []

    await bus.publish(PushEvent(kind="reminder_fired", payload={"id": "r-poll-1"}))
    third = await bus.poll_since(first["latest_seq"])
    assert len(third["events"]) == 1
    assert third["events"][0]["payload"]["id"] == "r-poll-1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_parse_repeat_interval() -> None:
    assert parse_repeat_interval("每5分钟提醒我喝水") == timedelta(minutes=5)
    assert parse_repeat_interval("every 2 hours stretch") == timedelta(hours=2)
    assert parse_repeat_interval("三分钟后喝水") is None


def test_extract_reminder_body_strips_repeat_phrase() -> None:
    assert extract_reminder_body("3分钟后每5分钟提醒我喝水") == "喝水"


@pytest.mark.asyncio
async def test_set_reminder_with_repeat_interval() -> None:
    result = await set_reminder(
        {
            "user_id": "repeat-user",
            "raw_text": "3分钟后每5分钟提醒我喝水",
        }
    )
    assert result.ok, result.message
    assert result.data.get("repeat_interval_seconds") == 300
    rem = result.data["reminder"]
    assert rem.get("repeat_interval_seconds") == 300


@pytest.mark.asyncio
async def test_repeating_reminder_scheduler_bumps_fire_at() -> None:
    store = RemindersStore()
    now = datetime.now(timezone.utc)
    r = await store.add(
        user_id="bump-user",
        text="周期喝水",
        fire_at=now - timedelta(seconds=2),
        repeat_interval_seconds=120,
    )
    scheduler = ReminderScheduler(poll_interval=999)
    received: list[dict] = []
    done = asyncio.Event()

    async def _consume(bus: ProactivePushBus) -> None:
        async for event in bus.subscribe():
            if event.kind == "reminder_fired" and event.payload.get("id") == r.id:
                received.append(event.payload)
                done.set()
                return

    consumer = asyncio.create_task(_consume(scheduler._bus))  # noqa: SLF001
    await asyncio.sleep(0.05)
    await scheduler._tick_once()  # noqa: SLF001
    try:
        await asyncio.wait_for(done.wait(), timeout=3)
    finally:
        consumer.cancel()

    assert received and received[0].get("repeating") is True
    updated = await store.get(r.id)
    assert updated is not None
    assert updated.fired_at is None
    assert updated.fire_at > now + timedelta(seconds=60)


def test_parse_relative_delay_handles_chinese_and_english() -> None:
    assert parse_relative_delay("3 分钟后") == timedelta(minutes=3)
    assert parse_relative_delay("10秒钟以后") == timedelta(seconds=10)
    assert parse_relative_delay("半小时后") is None  # non-numeric, expected miss
    assert parse_relative_delay("in 2 hours") == timedelta(hours=2)
    assert parse_relative_delay("没有时间词") is None


def test_extract_reminder_body_strips_prefix_and_delay() -> None:
    assert extract_reminder_body("提醒我3分钟后喝水") == "喝水"
    assert extract_reminder_body("帮我提醒 10 分钟后下楼拿快递") == "下楼拿快递"
    assert extract_reminder_body("remind me in 5 minutes to stretch") == "to stretch"
