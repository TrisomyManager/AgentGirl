"""Cross-module integration belongs to the reference host, not the memory module."""

from unittest.mock import AsyncMock
from uuid import uuid4

from core_orchestrator.runtime_hooks import apply_consolidated_profile
from shared_contracts.models import MemoryEntry
from shared_runtime.database import init_database_schema
from user_profile import UserProfileSnapshot, get_default_store


async def test_old_daily_preferences_cannot_override_a_newer_explicit_preference():
    user = uuid4().hex
    store = get_default_store()
    await init_database_schema()
    await store.upsert(
        UserProfileSnapshot(
            user_id=user,
            preferences={
                "latest_like": "茶",
                "likes": ["茶"],
                "latest_like_observed_at": "2026-10-20T02:00:00+00:00",
            },
        )
    )
    await apply_consolidated_profile(
        user,
        {
            "likes": ["咖啡"],
            "dislikes": [],
            "observed_at": "2026-10-19T02:00:00+00:00",
        },
    )
    profile = await store.get(user)
    assert profile.preferences["latest_like"] == "茶"
    assert profile.preferences["likes"] == ["茶"]


async def test_followup_does_not_surface_a_dormant_memory(monkeypatch):
    from core_orchestrator.runtime_hooks import memory_followup_context

    monkeypatch.setattr(
        "core_orchestrator.runtime_hooks.list_user_memories",
        AsyncMock(
            return_value=[
                MemoryEntry(
                    entry_id="old",
                    user_id="u",
                    category="fact",
                    content="旧约定",
                    importance=0.9,
                    memory_status="dormant",
                ),
                MemoryEntry(entry_id="current", user_id="u", category="fact", content="当前约定", importance=0.8),
            ]
        ),
    )
    assert (await memory_followup_context("u"))["memory_content"] == "当前约定"


async def test_reaction_precedes_generation_and_reply_tone_cannot_overwrite_it(monkeypatch):
    from core_orchestrator.state_machine import build_initial_state, node_generate_response
    from persona_engine.emotion_engine import EmotionEngine
    from persona_engine.relationship_tracker import RelationshipTracker
    from persona_engine.state_store import PersonaStateStore
    from shared_contracts.models import PersonaProfile, Platform, RelationshipMetrics, TurnContext, UserProfile
    from shared_runtime.database import AsyncSessionLocal

    store = PersonaStateStore(AsyncSessionLocal)
    engine = EmotionEngine(state_store=store)
    monkeypatch.setattr("persona_engine.runtime._emotion_engine", engine)
    monkeypatch.setattr("persona_engine.runtime._relationship_tracker", RelationshipTracker(state_store=store))
    monkeypatch.setattr("core_orchestrator.state_machine._is_monolithic", lambda: True)
    llm = AsyncMock()
    llm.has_configured_provider = lambda: True
    llm.generate.return_value = {"assistant_message": "哈哈真开心，太好啦！"}
    monkeypatch.setattr("shared_runtime.llm_client.LLMClient", lambda: llm)
    user = uuid4().hex
    context = TurnContext(
        turn_id=uuid4().hex,
        session_id=uuid4().hex,
        user=UserProfile(user_id=user),
        user_message="我难过想哭",
        platform=Platform.APP,
    )
    state = build_initial_state(context)
    state.update(
        persona_profile=PersonaProfile(name="Companion"),
        emotion_state=await engine.get_current_emotion(user),
        relationship_metrics=RelationshipMetrics(user_id=user),
    )
    result = await node_generate_response(state)
    assert result["reaction_signal"].sentiment == "negative"
    assert result["emotion_state"].valence < 0
    assert llm.generate.call_args.kwargs["temperature"] == 0.45
    assert "不使用 emoji" in llm.generate.call_args.kwargs["system_prompt"]
    assert await store.get_emotion(user) is None  # generation alone is not a completed turn
    llm.close.assert_awaited_once()


async def test_stream_uses_the_same_context_sensitive_response_policy(monkeypatch):
    from core_orchestrator.state_machine import _stream_response_monolithic
    from shared_contracts.models import EmotionState, TurnContext, UserProfile

    llm = AsyncMock()
    llm.has_configured_provider = lambda: True

    async def tokens(**kwargs):
        assert kwargs["temperature"] == 0.45
        assert "不使用 emoji" in kwargs["system_prompt"]
        yield "我在听"

    llm.generate_stream = tokens
    monkeypatch.setattr("shared_runtime.llm_client.LLMClient", lambda: llm)
    context = TurnContext(
        turn_id="t", session_id="s", user=UserProfile(user_id="u"), user_message="我失眠了", platform="app"
    )
    text = "".join(
        [
            token
            async for token in _stream_response_monolithic(
                context, "陪伴", emotion=EmotionState(primary="happy", valence=0.9, arousal=0.8)
            )
        ]
    )
    assert text == "我在听"
    llm.close.assert_awaited_once()


def test_expression_respects_serious_context_even_when_the_companion_is_still_happy():
    from core_orchestrator.orchestrator import Orchestrator
    from shared_contracts.models import EmotionState, TurnContext, UserProfile

    context = TurnContext(
        turn_id="t", session_id="s", user=UserProfile(user_id="u"), user_message="我昨晚失眠了", platform="app"
    )
    result = Orchestrator()._build_success_result(
        context,
        {
            "emotion_state": EmotionState(primary="happy", valence=0.9, arousal=0.8),
            "assistant_message": "我在听",
        },
    )
    assert result["expression_emoji"] is None
