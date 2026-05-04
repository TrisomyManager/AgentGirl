"""Tests for shared prompt assembly helpers."""

from __future__ import annotations

from datetime import datetime

from shared.models import EmotionState, EmotionTag, MemoryCategory, MemoryEntry, MemoryRecallResult, PersonaProfile, RelationshipMetrics
from shared.prompt_engine import build_base_system_prompt, build_conversation_system_prompt


def test_build_base_system_prompt_without_persona() -> None:
    prompt = build_base_system_prompt()
    assert "warm, emotionally aware companion AI" in prompt


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

    assert "You are 小暖" in prompt
    assert "Communication style:" in prompt
    assert "Relationship state:" in prompt
    assert "User summary:" in prompt
    assert "Relevant memories:" in prompt
    assert "Known facts:" in prompt
