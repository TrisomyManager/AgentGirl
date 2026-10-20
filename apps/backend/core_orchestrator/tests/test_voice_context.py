from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from core_orchestrator.runtime_hooks import persist_voice_turn, prepare_voice_conversation
from memory_system.working import get_working_memory
from persona_engine.emotion_engine import EmotionEngine
from persona_engine.relationship_tracker import RelationshipTracker
from persona_engine.state_store import PersonaStateStore
from shared_contracts.models import PersonaProfile
from shared_runtime.database import AsyncSessionLocal, init_database_schema
from user_profile import UserProfileSnapshot, get_default_store


async def test_voice_uses_text_persona_memories_and_reaction_then_commits_same_turn(monkeypatch):
    from shared_runtime.config import get_settings

    monkeypatch.setattr(get_settings(), "monolithic", True)
    monkeypatch.setattr(get_settings(), "enable_memory_pipeline", False)
    user, session_id, turn_id = (uuid4().hex for _ in range(3))
    profiles = get_default_store()
    await init_database_schema()
    await profiles.upsert(UserProfileSnapshot(user_id=user, preferences={"role_id": "tea-companion"}))
    selected = []

    def persona(*, role_id):
        selected.append(role_id)
        return PersonaProfile(name="茶友", core_traits=["耐心倾听"])

    monkeypatch.setattr("persona_engine.persona_store.get_persona_profile", persona)
    store = PersonaStateStore(AsyncSessionLocal)
    monkeypatch.setattr("persona_engine.runtime._emotion_engine", EmotionEngine(state_store=store))
    monkeypatch.setattr("persona_engine.runtime._relationship_tracker", RelationshipTracker(state_store=store))
    recall = AsyncMock(return_value=httpx.Response(200, json={
        "entries": [{"entry_id": "tea", "user_id": user, "category": "preference", "content": "用户喜欢茶"}],
    }))
    monkeypatch.setattr("core_orchestrator.state_machine.memory_client.post", recall)
    context = await prepare_voice_conversation(
        user_id=user, session_id=session_id, user_message="我难过又失眠了", turn_id=turn_id,
    )
    assert selected == ["tea-companion"]
    assert "茶友" in context.system_prompt and "用户喜欢茶" in context.system_prompt
    assert "不能执行工具" in context.system_prompt
    assert "直接确认并执行" not in context.system_prompt
    assert context.temperature == 0.45
    assert recall.call_args.kwargs["json_payload"]["user_id"] == user
    assert await store.get_emotion(user) is None
    await persist_voice_turn(
        user_id=user, session_id=session_id, turn_id=turn_id, user_message="我难过又失眠了",
        assistant_message="我在听，慢慢说。", memory_channel="voice_call", conversation_context=context,
    )
    emotion = await store.get_emotion(user)
    assert emotion.valence < 0
    history = await get_working_memory().snapshot(session_id)
    assert history.turns[-1].turn_id == turn_id
    assert history.turns[-1].user_message == "我难过又失眠了"
    await persist_voice_turn(
        user_id=user, session_id=session_id, turn_id=turn_id, user_message="我难过又失眠了",
        assistant_message="我在听，慢慢说。", memory_channel="voice_call", conversation_context=context,
    )
    assert (await store.get_relationship(user)).total_interactions == 1
    assert len((await get_working_memory().snapshot(session_id)).turns) == 1


async def test_native_completion_classifies_actual_transcript_not_initial_empty_context(monkeypatch):
    from shared_runtime.config import get_settings
    from voice_layer.conversation_context import VoiceConversationContext

    monkeypatch.setattr(get_settings(), "monolithic", True)
    monkeypatch.setattr(get_settings(), "enable_memory_pipeline", False)
    await init_database_schema()
    user, session_id = uuid4().hex, uuid4().hex
    store = PersonaStateStore(AsyncSessionLocal)
    monkeypatch.setattr("persona_engine.runtime._emotion_engine", EmotionEngine(state_store=store))
    monkeypatch.setattr("persona_engine.runtime._relationship_tracker", RelationshipTracker(state_store=store))
    await persist_voice_turn(
        user_id=user, session_id=session_id, turn_id=uuid4().hex, user_message="我难过想哭",
        assistant_message="哈哈真开心", memory_channel="voice_call",
        conversation_context=VoiceConversationContext("初始上下文"),
    )
    assert (await store.get_emotion(user)).valence < 0


async def test_voice_cannot_read_a_different_users_session_history():
    from memory_system.session_store import PersistentSessionMemory

    sid = uuid4().hex
    await PersistentSessionMemory().add_turn(
        sid, uuid4().hex, "另一位用户的私人约定", "记住了", metadata={"user_id": "alice"},
    )
    with pytest.raises(PermissionError):
        await prepare_voice_conversation(user_id="bob", session_id=sid, user_message="你好", turn_id=uuid4().hex)


async def test_recent_voice_recall_uses_conversation_context_instead_of_compact_memory_listing(monkeypatch):
    from action_executor.registry import get_registry
    from core_orchestrator.state_machine import _try_action_executor
    from shared_contracts.models import TurnContext, UserProfile

    dispatch = AsyncMock()
    monkeypatch.setattr(get_registry(), "dispatch", dispatch)
    context = TurnContext(
        turn_id=uuid4().hex, session_id=uuid4().hex, user=UserProfile(user_id=uuid4().hex),
        user_message="刚刚语音通话里，我说的下一个旅行城市是哪里？", platform="app",
    )
    assert await _try_action_executor(context, "memory_query") is None
    dispatch.assert_not_awaited()
