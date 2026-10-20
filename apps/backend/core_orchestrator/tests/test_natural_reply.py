"""Host integration: quiet turns remain observed without generation, audio or actions."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from core_orchestrator import state_machine as sm
from core_orchestrator.orchestrator import Orchestrator
from memory_system.session_store import PersistentSessionMemory
from memory_system.working import WorkingMemory
from persona_engine.conversation_preferences import ConversationPreferences, ConversationPreferencesStore
from persona_engine.emotion_engine import EmotionEngine
from persona_engine.relationship_tracker import RelationshipTracker
from persona_engine.state_store import PersonaStateStore
from shared_contracts.models import MemoryRecallResult, PersonaProfile, TurnContext, UserProfile, WorkingMemorySnapshot
from shared_runtime.config import get_settings
from shared_runtime.database import AsyncSessionLocal, init_database_schema


@pytest.fixture
async def host(monkeypatch):
    from action_executor.proactive_preferences import care_preferences_store  # noqa: F401

    await init_database_schema()
    user, sid = uuid4().hex, uuid4().hex
    store = PersonaStateStore(AsyncSessionLocal)
    await store.initialize()
    tracker = RelationshipTracker(state_store=store)
    monkeypatch.setattr("persona_engine.runtime._emotion_engine", EmotionEngine(state_store=store))
    monkeypatch.setattr("persona_engine.runtime._relationship_tracker", tracker)
    preferences = ConversationPreferencesStore()
    await preferences.save(
        user, ConversationPreferences(natural_reply_enabled=True, acknowledgement_reply_probability=0)
    )
    monkeypatch.setattr("persona_engine.conversation_preferences.conversation_preferences_store", preferences)
    monkeypatch.setattr(sm, "_is_monolithic", lambda: True)
    monkeypatch.setattr(get_settings(), "enable_memory_pipeline", False)
    memory = WorkingMemory()
    monkeypatch.setattr("memory_system.working.get_working_memory", lambda: memory)
    await memory.observe_turn(sid, "previous", "公园散步很舒服", "是很放松的一段时光。", user_id=user, intent="chat")

    async def classify(state):
        state["intent"] = "chat"
        return state

    async def recall(state):
        snapshot = await memory.snapshot(sid)
        state.update(
            persona_profile=PersonaProfile(name="Companion"),
            memory_result=MemoryRecallResult(
                entries=[],
                working_memory=WorkingMemorySnapshot(
                    session_id=sid,
                    recent_turns=[vars(turn) for turn in snapshot.turns],
                ),
            ),
        )
        return state

    async def identity(state):
        return state

    monkeypatch.setattr(sm, "node_classify_intent", classify)
    monkeypatch.setattr(sm, "node_recall_memory", recall)
    generation = AsyncMock(return_value="我在听")
    monkeypatch.setattr(sm, "_generate_response_monolithic", generation)
    voice, action = AsyncMock(side_effect=identity), AsyncMock(side_effect=identity)
    monkeypatch.setattr(sm, "node_synthesize_voice", voice)
    monkeypatch.setattr(sm, "node_generate_action", action)
    monkeypatch.setattr(sm, "node_send_response", identity)
    orchestrator = Orchestrator()
    orchestrator._graph = sm.build_graph()

    def context(message="嗯", **flags):
        return TurnContext(
            turn_id=uuid4().hex,
            session_id=sid,
            user=UserProfile(user_id=user),
            user_message=message,
            platform="app",
            **flags,
        )

    return orchestrator, context, generation, voice, action, tracker, memory


async def test_quiet_turn_skips_generation_preserves_history_and_prevents_consecutive_silence(host):
    orchestrator, context, generation, voice, action, tracker, memory = host
    first = context()
    result = await orchestrator.process_turn(first)
    assert result["reply_suppressed"] is True and result["assistant_message"] == ""
    assert result["talk_value"] == 0 and result["error"] is None
    generation.assert_not_awaited()
    voice.assert_not_awaited()
    action.assert_not_awaited()
    assert (await tracker.get_metrics(first.user.user_id)).total_interactions == 1
    archived = await PersistentSessionMemory().get_session_turns(first.session_id)
    assert archived[-1]["user_message"] == "嗯" and archived[-1]["assistant_message"] == ""
    assert archived[-1]["metadata"]["reply_suppressed"] is True
    assert (await memory.snapshot(first.session_id)).turns[-1].assistant_message == ""
    second = await orchestrator.process_turn(context("好的"))
    assert second["reply_suppressed"] is False and second["assistant_message"] == "我在听"
    generation.assert_awaited_once()


async def test_stream_quiet_turn_has_meta_and_done_without_tokens_or_voice(host):
    orchestrator, context, generation, voice, action, tracker, _ = host
    tc = context()
    events = [event async for event in orchestrator.process_turn_stream(tc)]
    assert [event["event"] for event in events] == ["meta", "done"]
    assert events[0]["reply_suppressed"] is True
    assert events[-1]["reply_suppressed"] is True
    assert events[-1]["expression_emoji"] is None
    assert events[-1]["assistant_message"] == ""
    assert events[-1]["voice_url"] is None
    voice.assert_not_awaited()
    action.assert_not_awaited()
    generation.assert_not_awaited()
    assert (await tracker.get_metrics(tc.user.user_id)).total_interactions == 1


async def test_unavailable_preferences_fail_open_and_voice_requests_still_reply(host, monkeypatch):
    orchestrator, context, generation, *_ = host
    first = await orchestrator.process_turn(context(request_voice_reply=True))
    assert first["reply_suppressed"] is False
    monkeypatch.setattr(ConversationPreferencesStore, "get", AsyncMock(side_effect=RuntimeError("unavailable")))
    second = await orchestrator.process_turn(context())
    assert second["reply_suppressed"] is False
    assert generation.await_count == 2


async def test_care_activity_failure_does_not_drop_the_persona_observation(host, monkeypatch):
    orchestrator, context, _, _, _, tracker, _ = host
    monkeypatch.setattr(
        "action_executor.proactive_preferences.care_preferences_store.touch",
        AsyncMock(side_effect=RuntimeError("activity unavailable")),
    )
    tc = context()
    assert (await orchestrator.process_turn(tc))["reply_suppressed"]
    assert (await tracker.get_metrics(tc.user.user_id)).total_interactions == 1


async def test_observe_turn_endpoint_preserves_remote_quiet_turns_once_without_generating_text():
    import httpx
    from fastapi import FastAPI

    from persona_engine.api import router

    store = PersonaStateStore(AsyncSessionLocal)
    tracker = RelationshipTracker(state_store=store)
    app = FastAPI()
    app.include_router(router)
    app.state.emotion_engine = EmotionEngine(state_store=store)
    app.state.relationship_tracker = tracker
    user = uuid4().hex
    payload = {"user_id": user, "turn_id": "quiet", "user_message": "嗯"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(2):
            response = await client.post("/persona/observe_turn", json=payload)
            assert response.status_code == 200
            assert response.json()["relationship"]["total_interactions"] == 1
