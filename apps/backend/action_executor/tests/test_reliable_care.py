"""Reliability contracts: crash recovery, atomic reminders, user controls and timezones."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from action_executor.api import router
from action_executor.proactive_care import ProactiveCareScheduler
from action_executor.proactive_preferences import CarePreferences, CarePreferencesStore, care_preferences_store
from action_executor.push_bus import DurableEventStore, ProactivePushBus, PushEvent
from action_executor.reminders import RemindersStore
from shared_runtime.database import init_database_schema


@pytest.fixture(autouse=True)
async def schema():
    await init_database_schema()


async def test_outbox_survives_recreated_bus_and_filters_users():
    user = uuid4().hex
    other = uuid4().hex
    bus = ProactivePushBus(DurableEventStore())
    await bus.publish(PushEvent("proactive_message", {"id": uuid4().hex, "user_id": user, "message": "记得休息"}))
    await bus.publish(PushEvent("proactive_message", {"id": uuid4().hex, "user_id": other, "message": "other"}))
    restarted = ProactivePushBus(DurableEventStore())
    snapshot = await restarted.poll_since(0, user)
    assert snapshot["durable"] is True
    assert [e["payload"]["message"] for e in snapshot["events"]] == ["记得休息"]
    assert (await restarted.poll_since(snapshot["latest_seq"], user))["events"] == []


async def test_pagination_does_not_skip_undelivered_events():
    store = DurableEventStore()
    user = uuid4().hex
    for number in range(5):
        await store.append(PushEvent("test", {"user_id": user, "number": number}))
    cursor = 0
    numbers = []
    while True:
        page = await store.poll_since(cursor, user, limit=2)
        numbers.extend(e["payload"]["number"] for e in page["events"])
        cursor = page["latest_seq"]
        if not page["has_more"]:
            break
    assert numbers == list(range(5))


async def test_repeated_publish_is_idempotent():
    store = DurableEventStore()
    user = uuid4().hex
    payload = {"id": uuid4().hex, "user_id": user, "fire_at": "2026-10-19T10:00:00+00:00"}
    assert await store.append(PushEvent("reminder_fired", dict(payload)))
    assert not await store.append(PushEvent("reminder_fired", dict(payload)))
    assert len((await store.poll_since(0, user))["events"]) == 1


async def test_completion_and_push_rollback_together():
    store = RemindersStore()
    reminder = await store.add(uuid4().hex, "喝水", datetime.now(UTC) - timedelta(seconds=1))
    broken_outbox = AsyncMock()
    broken_outbox.enqueue.side_effect = RuntimeError("storage unavailable")
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await store.fire_into_outbox(reminder, broken_outbox)
    assert (await store.get(reminder.id)).status == "pending"
    event = await store.fire_into_outbox(reminder, DurableEventStore())
    assert event is not None
    assert (await store.get(reminder.id)).status == "fired"
    assert await store.fire_into_outbox(reminder, DurableEventStore()) is None
    assert len((await DurableEventStore().poll_since(0, reminder.user_id))["events"]) == 1


async def test_cancelled_and_stale_repeating_occurrences_cannot_fire():
    store = RemindersStore()
    reminder = await store.add(
        uuid4().hex, "休息", datetime.now(UTC) - timedelta(seconds=1), repeat_interval_seconds=60
    )
    assert await store.fire_into_outbox(reminder, DurableEventStore()) is not None
    assert await store.fire_into_outbox(reminder, DurableEventStore()) is None
    current = await store.get(reminder.id)
    assert current.fire_at > datetime.now(UTC)
    assert await store.cancel(reminder.id, reminder.user_id)
    assert await store.fire_into_outbox(current, DurableEventStore()) is None


async def test_preferences_and_activity_survive_store_recreation():
    user = uuid4().hex
    preferences = CarePreferences(enabled=False, timezone="Asia/Shanghai", max_per_day=0)
    await care_preferences_store.save(user, preferences)
    await care_preferences_store.touch(user, "real-session")
    recreated = CarePreferencesStore()
    assert await recreated.get(user) == preferences
    last_seen, session_id = await recreated.activity(user)
    assert session_id == "real-session"
    assert last_seen is not None and last_seen.tzinfo is not None
    assert user in await recreated.users()


async def test_disabled_care_and_local_dnd_do_not_generate():
    user = uuid4().hex
    scheduler = ProactiveCareScheduler()
    scheduler._store = AsyncMock()
    now = datetime(2026, 10, 19, 15, 0, tzinfo=UTC)  # Shanghai 23:00
    await care_preferences_store.save(
        user, CarePreferences(timezone="Asia/Shanghai", dnd_start_hour=22, dnd_end_hour=7)
    )
    assert await scheduler._evaluate_user(user, now, False) == 0
    scheduler._store.last_sent_for_user.assert_not_called()
    await care_preferences_store.save(user, CarePreferences(enabled=False, dnd_start_hour=0, dnd_end_hour=0))
    assert await scheduler._evaluate_user(user, now, False) == 0


async def test_preferences_api_roundtrip_and_validation():
    app = FastAPI()
    app.include_router(router)
    user = uuid4().hex
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        path = f"/actions/proactive/preferences/{user}"
        original = (await client.get(path)).json()
        desired = original | {"enabled": False, "morning_greeting": False, "timezone": "Asia/Shanghai"}
        assert (await client.put(path, json=desired)).status_code == 200
        assert (await client.get(path)).json() == desired
        assert (await client.put(path, json=desired | {"timezone": "invalid/zone"})).status_code == 422
        assert (await client.put(path, json=desired | {"max_per_day": -1})).status_code == 422
        rules = (await client.get(f"/actions/user_state?user_id={user}")).json()["proactive"]["rules"]
        assert all(not rule["enabled"] for rule in rules)


def test_preferences_reject_unknown_fields_and_invalid_timezones():
    with pytest.raises(ValidationError):
        CarePreferences(timezone="somewhere")
    with pytest.raises(ValidationError):
        CarePreferences(api_key="not-a-setting")


async def test_slow_user_does_not_block_other_users_and_stop_cancels_workers():
    scheduler = ProactiveCareScheduler(poll_interval=0.01)
    blocked = asyncio.Event()
    progressed = asyncio.Event()
    scheduler._resolve_user_ids = AsyncMock(return_value=["slow", "fast"])

    async def evaluate(user_id, *_):
        if user_id == "slow":
            await blocked.wait()
        else:
            progressed.set()
        return 0

    scheduler._evaluate_user = evaluate
    await scheduler.start()
    try:
        await asyncio.wait_for(progressed.wait(), timeout=1)
        assert len(scheduler._user_tasks) == 2
    finally:
        await scheduler.stop()
    assert scheduler._task is None
    assert scheduler._user_tasks == {}


async def test_proactive_log_and_delivery_commit_together():
    scheduler = ProactiveCareScheduler()
    user = uuid4().hex
    await care_preferences_store.save(user, CarePreferences(dnd_start_hour=0, dnd_end_hour=0))
    scheduler._call_orchestrator = AsyncMock(return_value={"assistant_message": "今天辛苦啦", "session_id": "s"})
    assert await scheduler._fire_proactive(user, "evening_greeting", {}, datetime.now(UTC))
    restarted = ProactivePushBus(DurableEventStore())
    events = (await restarted.poll_since(0, user))["events"]
    assert len(events) == 1
    assert events[0]["payload"]["message"] == "今天辛苦啦"
    logs = await scheduler._store.list_for_user(user)
    assert events[0]["payload"]["id"] == logs[0].id


async def test_preferences_disabled_during_generation_prevents_delivery():
    scheduler = ProactiveCareScheduler()
    user = uuid4().hex
    await care_preferences_store.save(user, CarePreferences(dnd_start_hour=0, dnd_end_hour=0))

    async def generate(**_):
        await care_preferences_store.save(user, CarePreferences(enabled=False))
        return {"assistant_message": "不应送出"}

    scheduler._call_orchestrator = generate
    assert not await scheduler._fire_proactive(user, "idle_checkin", {}, datetime.now(UTC))
    assert (await DurableEventStore().poll_since(0, user))["events"] == []


async def test_memory_followup_is_not_starved_by_idle_greeting():
    scheduler = ProactiveCareScheduler()
    user = uuid4().hex
    now = datetime.now(UTC)
    await care_preferences_store.save(user, CarePreferences(dnd_start_hour=0, dnd_end_hour=0))
    scheduler._store = AsyncMock()
    scheduler._store.last_sent_for_user.return_value = None
    scheduler._store.count_today.return_value = 0
    scheduler._get_user_last_seen = AsyncMock(return_value=now - timedelta(days=6))
    scheduler._get_memory_followup_context = AsyncMock(return_value={"memory_content": "面试"})
    scheduler._fire_proactive = AsyncMock(return_value=True)
    assert await scheduler._evaluate_user(user, now, False) == 1
    assert scheduler._fire_proactive.call_args.kwargs["trigger_type"] == "memory_followup"


async def test_reduced_daily_limit_during_generation_prevents_delivery():
    scheduler = ProactiveCareScheduler()
    user = uuid4().hex
    await care_preferences_store.save(user, CarePreferences(dnd_start_hour=0, dnd_end_hour=0))

    async def generate(**_):
        await care_preferences_store.save(user, CarePreferences(max_per_day=0, dnd_start_hour=0, dnd_end_hour=0))
        return {"assistant_message": "不应发送"}

    scheduler._call_orchestrator = generate
    assert not await scheduler._fire_proactive(user, "idle_checkin", {}, datetime.now(UTC))
    assert (await DurableEventStore().poll_since(0, user))["events"] == []
