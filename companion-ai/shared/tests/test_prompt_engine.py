"""Tests for shared prompt assembly helpers."""

from __future__ import annotations

from datetime import datetime

from shared.models import EmotionState, EmotionTag, MemoryCategory, MemoryEntry, MemoryRecallResult, PersonaProfile, RelationshipMetrics
from shared.prompt_engine import build_base_system_prompt, build_conversation_system_prompt


def test_build_base_system_prompt_without_persona() -> None:
    prompt = build_base_system_prompt()
    assert "小暖" in prompt
    assert "陪伴者" in prompt


def test_build_base_system_prompt_with_persona_uses_name() -> None:
    persona = PersonaProfile(name="星野")
    prompt = build_base_system_prompt(persona=persona)
    assert "星野" in prompt
    assert "陪伴者" in prompt


def test_build_conversation_system_prompt_includes_context() -> None:
    persona = PersonaProfile(
        name="小暖",
        communication_style="温柔自然，像一位知心朋友。",
        core_traits=["温柔", "善于倾听"],
        values=["真诚", "陪伴"],
        backstory="诞生于数字花园。",
        relationship_goals=["安心倾诉", "记住小事"],
    )
    emotion = EmotionState(
        primary=EmotionTag.CALM,
        intensity=0.4,
        valence=0.3,
        arousal=0.2,
    )
    relationship = RelationshipMetrics(
        user_id="u1",
        intimacy=0.7,
        trust=0.8,
        familiarity=0.6,
        affection=0.75,
        total_interactions=12,
    )
    memory = MemoryRecallResult(
        entries=[
            MemoryEntry(
                entry_id="m1",
                user_id="u1",
                category=MemoryCategory.PREFERENCE,
                content="User likes rainy days.",
                created_at=datetime.utcnow(),
            )
        ],
        graph_facts=["User has a cat named Mimi."],
        user_profile_summary="Prefers quiet evenings and warm drinks.",
    )

    prompt = build_conversation_system_prompt(
        persona=persona,
        emotion=emotion,
        relationship=relationship,
        memory=memory,
    )

    assert "小暖" in prompt
    assert "【性格特点】" in prompt
    assert "温柔" in prompt
    assert "【沟通方式】" in prompt
    assert "温柔自然，像一位知心朋友。" in prompt
    assert "【价值观】" in prompt
    assert "真诚" in prompt
    assert "【关于你自己】" in prompt
    assert "诞生于数字花园。" in prompt
    assert "【关系目标】" in prompt
    assert "安心倾诉" in prompt
    assert "【当前情绪】" in prompt
    assert "平静" in prompt
    assert "【你们的关系】" in prompt
    assert "亲密度 0.70" in prompt
    assert "【用户概况】" in prompt
    assert "Prefers quiet evenings and warm drinks." in prompt
    assert "【记忆片段】" in prompt
    assert "User likes rainy days." in prompt
    assert "【已知事实】" in prompt
    assert "User has a cat named Mimi." in prompt
