"""Natural cancellation resolves the user's actual reminders, including ambiguous titles."""

from uuid import uuid4

import pytest

from action_executor.handlers import cancel_reminder, set_reminder
from action_executor.reminders import get_reminders_store
from shared_runtime.database import init_database_schema
from shared_runtime.reminder_language import cancellation_target


@pytest.fixture(autouse=True)
async def schema():
    await init_database_schema()


@pytest.mark.parametrize(
    "message,expected",
    [
        ("取消喝水的提醒", "喝水"),
        ("请你帮我取消喝水的提醒", "喝水"),
        ("不用再提醒我喝水了", "喝水"),
        ("以后不需要提醒我交材料了", "交材料"),
        ("取消所有提醒", "所有"),
        ("取消提醒", ""),
        ("不要取消喝水的提醒", None),
        ("先别创建提醒", None),
    ],
)
def test_cancellation_is_distinct_from_a_veto(message, expected):
    assert cancellation_target(message) == expected


async def add(user, text):
    result = await set_reminder({"user_id": user, "text": text, "delay_seconds": 3600})
    return result.data["reminder"]["id"]


async def test_cancellation_resolves_title_and_never_touches_a_different_users_reminder():
    user, other = uuid4().hex, uuid4().hex
    cancelled = await add(user, "喝水")
    kept = await add(user, "交材料")
    foreign = await add(other, "喝水")
    result = await cancel_reminder({"user_id": user, "raw_text": "不用再提醒我喝水了"})
    assert result.ok
    assert result.data["reminder_id"] == cancelled
    assert [item.id for item in await get_reminders_store().list_for_user(user)] == [kept]
    assert [item.id for item in await get_reminders_store().list_for_user(other)] == [foreign]


async def test_ambiguous_title_asks_for_a_choice_and_explicit_all_cancels_only_owners_pending_items():
    user, other = uuid4().hex, uuid4().hex
    await add(user, "下午喝水")
    await add(user, "晚上喝水")
    foreign = await add(other, "喝水")
    result = await cancel_reminder({"user_id": user, "raw_text": "取消喝水的提醒"})
    assert not result.ok and result.data["error"] == "ambiguous_reminder"
    assert len(await get_reminders_store().list_for_user(user)) == 2
    result = await cancel_reminder({"user_id": user, "raw_text": "取消所有提醒"})
    assert result.ok and result.data["cancelled_count"] == 2
    assert not await get_reminders_store().list_for_user(user)
    assert [item.id for item in await get_reminders_store().list_for_user(other)] == [foreign]
