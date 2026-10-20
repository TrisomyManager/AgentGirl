"""Opt-in probabilistic replies for acknowledgements; never delegate silence to an LLM."""

import hashlib
import re
from dataclasses import dataclass

from persona_engine.conversation_preferences import ConversationPreferences
from persona_engine.reaction import rule_reaction


@dataclass(frozen=True)
class ReplyDecision:
    should_reply: bool = True
    talk_value: float = 1.0
    reason: str = "normal_reply"


_ACKNOWLEDGEMENT = re.compile(r"(?:嗯+|哦+|好的?|好哒|好呀|收到|知道了|明白了|ok|okay|谢谢)[！!。.~～\s]*", re.I)
_AWAITING_INPUT = re.compile(r"[?？]|要不要|需不需要|请确认|请(?:你)?选择|你选|我可以|需要我|要我|我帮你|继续吗")


def decide_reply(
    preferences: ConversationPreferences,
    *,
    user_id: str,
    turn_id: str,
    user_message: str,
    intent="chat",
    reaction_intent="chat",
    has_voice=False,
    request_voice_reply=False,
    has_image=False,
    recent_turns=(),
    sample=None,
) -> ReplyDecision:
    """A deterministic per-turn draw makes retries stable across restarts.

    Hosts pass their actual recent context. With missing context we respond;
    generic acknowledgement classification alone never justifies silence.
    """
    if not preferences.natural_reply_enabled:
        return ReplyDecision(reason="natural_reply_disabled")
    if has_voice or request_voice_reply or has_image or intent != "chat":
        return ReplyDecision(reason="explicit_response_required")
    if reaction_intent in {"question", "task", "support"}:
        return ReplyDecision(reason="meaningful_reaction")
    if not _ACKNOWLEDGEMENT.fullmatch(user_message.strip()):
        return ReplyDecision(reason="meaningful_message")
    if not recent_turns:
        return ReplyDecision(reason="conversation_start")
    previous = recent_turns[-1]
    previous_assistant = str(previous.get("assistant_message") or "").strip()
    if not previous_assistant:
        return ReplyDecision(reason="avoid_consecutive_silence")
    if _AWAITING_INPUT.search(previous_assistant):
        return ReplyDecision(reason="awaiting_confirmation")
    if previous.get("intent") not in {None, "chat"}:
        return ReplyDecision(reason="task_context")
    if rule_reaction(str(previous.get("user_message") or "")).intent == "support":
        return ReplyDecision(reason="support_context")
    probability = preferences.acknowledgement_reply_probability
    if sample is None:
        digest = hashlib.sha256(f"{user_id}\0{turn_id}".encode()).digest()
        sample = int.from_bytes(digest[:8], "big") / (2**64)
    should_reply = probability >= 1 or (probability > 0 and sample < probability)
    return ReplyDecision(
        should_reply, probability, "acknowledgement_reply" if should_reply else "quiet_acknowledgement"
    )
