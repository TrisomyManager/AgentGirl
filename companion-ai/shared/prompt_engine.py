"""Prompt assembly helpers shared across companion-ai modules."""

from __future__ import annotations

from typing import List, Optional

from shared.models import EmotionState, MemoryRecallResult, PersonaProfile, RelationshipMetrics

_DEFAULT_NAME = "小暖"
_DEFAULT_BASE_PROMPT = "你是小暖，一个温柔体贴、善于倾听的陪伴者。请用自然温暖的中文回复。"

_EMOTION_ZH = {
    "calm": "平静",
    "happy": "开心",
    "sad": "难过",
    "angry": "生气",
    "anxious": "焦虑",
    "excited": "兴奋",
    "neutral": "平和",
    "surprised": "惊喜",
    "fearful": "害怕",
    "disgusted": "反感",
    "loving": "温柔",
    "curious": "好奇",
}


def build_base_system_prompt(persona: Optional[PersonaProfile] = None) -> str:
    """Return a lightweight default system prompt before memory/persona recall."""
    if persona is None:
        return _DEFAULT_BASE_PROMPT
    return f"你是{persona.name}，一个温柔体贴、善于倾听的陪伴者。请用自然温暖的中文回复。"


def _emotion_zh(tag: str) -> str:
    return _EMOTION_ZH.get(tag, tag)


def build_conversation_system_prompt(
    persona: Optional[PersonaProfile],
    emotion: Optional[EmotionState] = None,
    relationship: Optional[RelationshipMetrics] = None,
    memory: Optional[MemoryRecallResult] = None,
) -> str:
    """Build the full conversation system prompt used for response generation."""
    name = persona.name if persona else _DEFAULT_NAME
    parts: List[str] = [f"你是{name}，一个温柔体贴的陪伴者。请始终用自然流畅的中文回复，语气亲切温暖。"]

    if persona and persona.core_traits:
        trait_lines = "\n".join(f"- {t}" for t in persona.core_traits)
        parts.append(f"【性格特点】\n{trait_lines}")

    if persona and persona.communication_style:
        style = persona.communication_style.strip()
        parts.append(f"【沟通方式】\n{style}")

    if persona and persona.values:
        value_lines = "\n".join(f"- {v}" for v in persona.values)
        parts.append(f"【价值观】\n{value_lines}")

    if persona and persona.backstory:
        parts.append(f"【关于你自己】\n{persona.backstory.strip()}")

    if persona and persona.relationship_goals:
        goal_lines = "\n".join(f"- {g}" for g in persona.relationship_goals)
        parts.append(f"【关系目标】\n{goal_lines}")

    if emotion:
        emo_zh = _emotion_zh(emotion.primary.value)
        parts.append(
            f"【当前情绪】{emo_zh}（强度 {emotion.intensity:.2f}，"
            f"情感色彩 {emotion.valence:+.2f}，唤醒度 {emotion.arousal:.2f}）"
        )

    if relationship and relationship.total_interactions > 0:
        parts.append(
            f"【你们的关系】亲密度 {relationship.intimacy:.2f}，"
            f"信任度 {relationship.trust:.2f}，"
            f"熟悉度 {relationship.familiarity:.2f}，"
            f"共同经历 {relationship.total_interactions} 次对话"
        )

    if memory and memory.user_profile_summary:
        parts.append(f"【用户概况】{memory.user_profile_summary}")

    if memory and memory.entries:
        memory_lines = [entry.content for entry in memory.entries[:3]]
        parts.append("【记忆片段】\n- " + "\n- ".join(memory_lines))

    if memory and memory.graph_facts:
        parts.append("【已知事实】\n- " + "\n- ".join(memory.graph_facts[:3]))

    if memory and memory.working_memory:
        wm = memory.working_memory
        wm_bits: List[str] = []
        if wm.user_name:
            wm_bits.append(f"用户自称：{wm.user_name}")
        if wm.user_role:
            wm_bits.append(f"用户身份：{wm.user_role}")
        if wm.dominant_topic:
            wm_bits.append(f"近段聊的主题：{wm.dominant_topic}")
        if wm.last_user_emotion:
            wm_bits.append(f"用户上一句的情绪：{_emotion_zh(wm.last_user_emotion)}")
        if wm.likes:
            wm_bits.append("最近表达的喜好：" + "、".join(wm.likes[:3]))
        if wm.dislikes:
            wm_bits.append("最近表达的反感：" + "、".join(wm.dislikes[:3]))
        if wm.last_assistant_preview:
            wm_bits.append(f"你上一轮的话：{wm.last_assistant_preview}")
        if wm_bits:
            parts.append("【当前对话状态】\n- " + "\n- ".join(wm_bits))

        if wm.recent_turns:
            tail_turns = wm.recent_turns[-3:]
            tail_lines: List[str] = []
            for t in tail_turns:
                user_msg = (t.get("user_message") or "").strip().replace("\n", " ")
                assistant_msg = (t.get("assistant_message") or "").strip().replace("\n", " ")
                if user_msg:
                    tail_lines.append(f"用户：{user_msg}")
                if assistant_msg:
                    tail_lines.append(f"你：{assistant_msg}")
            if tail_lines:
                parts.append("【最近几轮对话】\n" + "\n".join(tail_lines))

    return "\n\n".join(parts)
