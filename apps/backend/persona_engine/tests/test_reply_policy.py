"""Product contracts for opt-in quiet acknowledgement and durable preferences."""

from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from persona_engine.conversation_preferences import ConversationPreferences, ConversationPreferencesStore
from persona_engine.reply_policy import decide_reply

RECENT = [{"user_message": "刚才我在公园散步", "assistant_message": "听起来是很舒服的一段时光。", "intent": "chat"}]


def decision(message="嗯", preferences=None, **overrides):
    return decide_reply(
        preferences or ConversationPreferences(natural_reply_enabled=True, acknowledgement_reply_probability=0),
        **({"user_id": "u", "turn_id": "t", "user_message": message, "recent_turns": RECENT} | overrides),
    )


def test_always_replies_by_default_and_probability_endpoints_are_exact():
    assert decision(preferences=ConversationPreferences()).should_reply
    assert not decision(sample=0).should_reply
    assert decision(
        preferences=ConversationPreferences(
            natural_reply_enabled=True,
            acknowledgement_reply_probability=1,
        ),
        sample=1,
    ).should_reply


@pytest.mark.parametrize(
    "message", ["嗯？", "好的，帮我继续", "你好", "我有点难过", "别不理我", "收到？", "thanks for helping me"]
)
def test_meaningful_messages_are_never_silenced_by_a_classifier_label(message):
    assert decision(message, reaction_intent="acknowledgement").should_reply


@pytest.mark.parametrize(
    "flags",
    [
        {"has_voice": True},
        {"request_voice_reply": True},
        {"has_image": True},
        {"intent": "tool_use"},
        {"intent": "memory_query"},
        {"reaction_intent": "support"},
        {"reaction_intent": "task"},
        {"reaction_intent": "question"},
        {"recent_turns": []},
    ],
)
def test_explicit_requests_and_first_contact_always_get_a_reply(flags):
    assert decision(**flags).should_reply


@pytest.mark.parametrize(
    "recent",
    [
        [{"assistant_message": "要不要我帮你安排明天的提醒？"}],
        [{"assistant_message": "我可以先帮你列一个计划。"}],
        [{"assistant_message": "请选择接下来要做的事。"}],
        [{"assistant_message": ""}],
        [{"assistant_message": "安排好了。", "intent": "tool_use"}],
        [{"assistant_message": "我一直在听。", "user_message": "我难过得想哭"}],
    ],
)
def test_confirmation_task_support_and_consecutive_silence_are_protected(recent):
    assert decision(recent_turns=recent).should_reply


def test_probability_is_stable_on_retry_and_varies_between_turns():
    prefs = ConversationPreferences(natural_reply_enabled=True, acknowledgement_reply_probability=0.35)
    first = [decision(preferences=prefs, turn_id=str(index)).should_reply for index in range(1000)]
    replay = [decision(preferences=prefs, turn_id=str(index)).should_reply for index in range(1000)]
    assert first == replay
    assert 300 < sum(first) < 400


async def test_preferences_survive_new_store_instances_and_are_user_scoped():
    user = uuid4().hex
    store = ConversationPreferencesStore()
    prefs = ConversationPreferences(natural_reply_enabled=True, acknowledgement_reply_probability=0.2)
    await store.save(user, prefs)
    restarted = ConversationPreferencesStore()
    assert await restarted.get(user) == prefs
    assert not (await restarted.get(uuid4().hex)).natural_reply_enabled


async def test_preferences_api_checks_values_and_preserves_saved_state_after_invalid_updates(monkeypatch):
    from persona_engine.api import router

    monkeypatch.setattr("persona_engine.api.conversation_preferences_store", ConversationPreferencesStore())
    app = FastAPI()
    app.include_router(router)
    user = uuid4().hex
    path = f"/persona/conversation_preferences/{user}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(path)).json()["natural_reply_enabled"] is False
        saved = {"natural_reply_enabled": True, "acknowledgement_reply_probability": 0.5}
        assert (await client.put(path, json=saved)).status_code == 200
        for invalid in (-0.1, 1.1, "NaN"):
            assert (
                await client.put(path, json={**saved, "acknowledgement_reply_probability": invalid})
            ).status_code == 422
        assert (await client.put(path, json={**saved, "extra_setting": True})).status_code == 422
        assert (await client.get(path)).json() == saved
