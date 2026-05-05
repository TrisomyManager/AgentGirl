"""Tests for the working-memory layer.

Covers:
  - WorkingMemory.observe_turn appends turns and refreshes the live summary.
  - Heuristic extractors pick up name / role / likes / dislikes / topic.
  - Snapshot survives an in-process cache invalidation by rebuilding
    from short_term backend.
  - build_conversation_system_prompt renders the 【当前对话状态】 and
    【最近几轮对话】 sections from a populated WorkingMemorySnapshot.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import List

import pytest

# These tests are deliberately Lite-mode only — the goal is to exercise the
# pure-Python path (in-memory short_term backend) without requiring Redis.
os.environ.setdefault("COMPANION_LITE_MODE", "true")

from memory_system.working import WorkingMemory, get_working_memory
from shared.models import (
    EmotionState,
    EmotionTag,
    MemoryRecallResult,
    PersonaProfile,
    RelationshipMetrics,
    WorkingMemorySnapshot,
)
from shared.prompt_engine import build_conversation_system_prompt


def _new_wm() -> WorkingMemory:
    """Use a fresh WorkingMemory per test to keep state isolated.

    The module-level singleton is reused by the orchestrator at runtime,
    but each test should start with a clean slate so previous tests don't
    bleed extra turns into our session.
    """
    return WorkingMemory(window_size=6)


@pytest.mark.asyncio
async def test_observe_turn_records_basic_state() -> None:
    wm = _new_wm()
    sid = f"sess-{uuid.uuid4()}"

    state = await wm.observe_turn(
        session_id=sid,
        turn_id="t1",
        user_message="嗨，你好呀",
        assistant_message="我在呢，今天怎么样？",
        emotion="neutral",
        intent="chat",
    )
    assert state.session_id == sid
    assert len(state.turns) == 1
    assert state.turns[0].user_message == "嗨，你好呀"
    assert state.last_user_emotion == "neutral"
    assert "我在呢" in (state.last_assistant_preview or "")


@pytest.mark.asyncio
async def test_window_size_trims_old_turns() -> None:
    wm = WorkingMemory(window_size=3)
    sid = f"sess-{uuid.uuid4()}"

    for i in range(5):
        await wm.observe_turn(
            session_id=sid,
            turn_id=f"t{i}",
            user_message=f"消息 {i}",
            assistant_message=f"回应 {i}",
            emotion="calm",
            intent="chat",
        )

    state = await wm.snapshot(sid)
    assert len(state.turns) == 3
    # newest three should be t2, t3, t4
    assert [t.turn_id for t in state.turns] == ["t2", "t3", "t4"]


@pytest.mark.asyncio
async def test_extracts_name_role_likes_dislikes() -> None:
    wm = _new_wm()
    sid = f"sess-{uuid.uuid4()}"

    await wm.observe_turn(
        session_id=sid,
        turn_id="t1",
        user_message="我叫小石头，我是一个工程师。",
        assistant_message="很高兴认识你，小石头。",
    )
    await wm.observe_turn(
        session_id=sid,
        turn_id="t2",
        user_message="我很喜欢下雨天，我讨厌加班。",
        assistant_message="我也觉得雨天的窗口很治愈。",
    )

    state = await wm.snapshot(sid)
    assert state.user_name == "小石头"
    assert state.user_role == "工程师"
    assert "下雨天" in state.likes
    assert "加班" in state.dislikes


@pytest.mark.asyncio
async def test_dominant_topic_picks_repeated_concept() -> None:
    wm = _new_wm()
    sid = f"sess-{uuid.uuid4()}"

    for i in range(3):
        await wm.observe_turn(
            session_id=sid,
            turn_id=f"t{i}",
            user_message=f"我最近在准备考试，考试压力好大",
            assistant_message="我先陪着你",
            emotion="anxious",
            intent="chat",
        )

    state = await wm.snapshot(sid)
    assert state.dominant_topic == "考试"


@pytest.mark.asyncio
async def test_snapshot_rebuilds_from_short_term_backend() -> None:
    """If the in-process summary cache is empty, snapshot should still
    return a state by rebuilding from the short_term backend."""
    wm = _new_wm()
    sid = f"sess-{uuid.uuid4()}"

    await wm.observe_turn(
        session_id=sid,
        turn_id="t1",
        user_message="我叫阿九",
        assistant_message="阿九你好",
    )

    # Drop the in-process cache, simulating a fresh process.
    wm._states.clear()  # noqa: SLF001 — internal hatch is fine in test

    state = await wm.snapshot(sid)
    assert state.user_name == "阿九"
    assert len(state.turns) == 1


@pytest.mark.asyncio
async def test_clear_wipes_session() -> None:
    wm = _new_wm()
    sid = f"sess-{uuid.uuid4()}"

    await wm.observe_turn(sid, "t1", "我叫莫名", "好的", emotion="calm", intent="chat")
    pre = await wm.snapshot(sid)
    assert pre.user_name == "莫名"

    await wm.clear(sid)
    post = await wm.snapshot(sid)
    assert post.turns == []
    assert post.user_name is None


def test_get_working_memory_returns_singleton() -> None:
    a = get_working_memory()
    b = get_working_memory()
    assert a is b


def test_prompt_renders_working_memory_section() -> None:
    snap = WorkingMemorySnapshot(
        session_id="sess-x",
        turn_count=2,
        user_name="阿九",
        user_role="设计师",
        likes=["阴雨天", "猫"],
        dislikes=["加班"],
        dominant_topic="设计",
        last_user_emotion="sad",
        last_assistant_preview="我在认真听你说。",
        recent_turns=[
            {
                "turn_id": "t1",
                "user_message": "我今天又被改稿了",
                "assistant_message": "辛苦你了",
                "emotion": "sad",
            },
            {
                "turn_id": "t2",
                "user_message": "我有点想哭",
                "assistant_message": "我在认真听你说。",
                "emotion": "sad",
            },
        ],
    )
    memory = MemoryRecallResult(entries=[], graph_facts=[], working_memory=snap)
    persona = PersonaProfile(name="小暖")
    emotion = EmotionState(primary=EmotionTag.CALM, intensity=0.4, valence=0.2, arousal=0.2)
    relationship = RelationshipMetrics(
        user_id="u1", intimacy=0.5, trust=0.5, familiarity=0.4, total_interactions=2
    )

    prompt = build_conversation_system_prompt(
        persona=persona,
        emotion=emotion,
        relationship=relationship,
        memory=memory,
    )

    assert "【当前对话状态】" in prompt
    assert "用户自称：阿九" in prompt
    assert "用户身份：设计师" in prompt
    assert "近段聊的主题：设计" in prompt
    # Chinese emotion translation should kick in via _emotion_zh
    assert "用户上一句的情绪：难过" in prompt
    assert "最近表达的喜好：" in prompt and "阴雨天" in prompt
    assert "最近表达的反感：" in prompt and "加班" in prompt
    assert "你上一轮的话：" in prompt and "我在认真听你说。" in prompt
    assert "【最近几轮对话】" in prompt
    assert "用户：我今天又被改稿了" in prompt
    assert "你：我在认真听你说。" in prompt


def test_prompt_omits_section_when_no_working_memory() -> None:
    """If working_memory is None, no 【当前对话状态】 section is emitted."""
    memory = MemoryRecallResult(entries=[], graph_facts=[], working_memory=None)
    persona = PersonaProfile(name="小暖")
    prompt = build_conversation_system_prompt(persona=persona, memory=memory)
    assert "【当前对话状态】" not in prompt
    assert "【最近几轮对话】" not in prompt
