"""Restart, rolling compression and deletion contracts without external services."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from memory_system.short_term import ShortTermMemory
from memory_system.working import WorkingMemory
from shared_contracts.models import MemoryRecallResult, PersonaProfile, WorkingMemorySnapshot
from shared_runtime.prompt_engine import build_conversation_system_prompt


@pytest.fixture(autouse=True)
def disable_network_summary(monkeypatch):
    monkeypatch.setattr(
        "memory_system.working.get_settings",
        lambda: SimpleNamespace(
            working_memory_llm_digest=False,
            working_memory_llm_summary=False,
        ),
    )


async def test_new_memory_objects_restore_turns_and_deduplicate_turn_ids():
    session_id = uuid4().hex
    first = ShortTermMemory()
    await first.add_turn(session_id, "one", "我叫小林", "你好", metadata={"user_id": "owner"})
    await first.add_turn(session_id, "one", "重复投递", "不应重复")
    restarted = ShortTermMemory()
    turns = await restarted.get_session_turns(session_id)
    assert len(turns) == 1
    assert turns[0]["user_message"] == "我叫小林"
    assert turns[0]["metadata"]["user_id"] == "owner"


async def test_evicted_user_facts_and_context_survive_restart_and_reach_prompt():
    session_id = uuid4().hex
    first = WorkingMemory(window_size=2)
    await first.observe_turn(session_id, "one", "我叫小林，我喜欢散步", "我记住了", user_id="owner")
    for number in range(2, 7):
        await first.observe_turn(session_id, str(number), f"第{number}轮的话题", "我在听", user_id="owner")
    restarted = WorkingMemory(window_size=2)
    restarted._short_term = ShortTermMemory()
    snapshot = await restarted.snapshot(session_id)
    assert snapshot.user_name == "小林"
    assert "散步" in snapshot.likes
    assert len(snapshot.turns) == 2
    assert "我叫小林" in snapshot.history_digest
    prompt_snapshot = WorkingMemorySnapshot(**snapshot.to_dict())
    prompt = build_conversation_system_prompt(
        persona=PersonaProfile(name="Companion"),
        memory=MemoryRecallResult(entries=[], working_memory=prompt_snapshot),
    )
    assert "更早对话摘要" in prompt
    assert "我叫小林" in prompt


async def test_clear_removes_durable_turns_and_compacted_summary():
    session_id = uuid4().hex
    first = WorkingMemory(window_size=1)
    await first.observe_turn(session_id, "one", "我叫小林", "你好")
    await first.observe_turn(session_id, "two", "最近在准备考试", "加油")
    assert (await first.snapshot(session_id)).history_digest
    await first.clear(session_id)
    restarted = WorkingMemory(window_size=1)
    restarted._short_term = ShortTermMemory()
    snapshot = await restarted.snapshot(session_id)
    assert snapshot.turns == []
    assert not snapshot.history_digest
    assert not snapshot.user_name


async def test_llm_compaction_failure_keeps_extractable_context(monkeypatch):
    session_id = uuid4().hex
    memory = WorkingMemory(window_size=1)
    await memory.observe_turn(session_id, "one", "下周要参加面试", "我陪你准备")

    class FailingLLM:
        def has_configured_provider(self):
            return True

        async def generate(self, **_):
            raise TimeoutError("unavailable")

    monkeypatch.setattr("shared_runtime.llm_client.LLMClient", FailingLLM)
    monkeypatch.setattr(
        "memory_system.working.get_settings",
        lambda: SimpleNamespace(
            working_memory_llm_digest=True,
            working_memory_compression_batch_turns=1,
            working_memory_llm_summary=False,
            working_memory_summary_model=None,
        ),
    )
    state = await memory.observe_turn(session_id, "two", "今天先休息", "好的")
    assert "下周要参加面试" in state.history_digest


async def test_old_turns_use_batched_model_compaction_without_losing_recent_window(monkeypatch):
    from unittest.mock import AsyncMock

    session_id = uuid4().hex
    memory = WorkingMemory(window_size=2)
    model = AsyncMock(return_value={"assistant_message": "用户在准备面试，想获得陪伴。"})

    class SummaryClient:
        def has_configured_provider(self):
            return True

        generate = model

    monkeypatch.setattr("shared_runtime.llm_client.LLMClient", SummaryClient)
    monkeypatch.setattr(
        "memory_system.working.get_settings",
        lambda: SimpleNamespace(
            working_memory_compression_use_llm=True,
            working_memory_compression_batch_turns=3,
            working_memory_llm_digest=False,
            working_memory_llm_summary=False,
            working_memory_summary_model=None,
        ),
    )
    for number in range(5):
        state = await memory.observe_turn(session_id, str(number), f"准备面试第{number}轮", "我陪你")
    model.assert_awaited_once()
    assert state.history_digest == "用户在准备面试，想获得陪伴。"
    assert [turn.turn_id for turn in state.turns] == ["3", "4"]
