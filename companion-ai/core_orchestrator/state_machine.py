"""LangGraph state machine for the conversation flow."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
from typing import Annotated, Any, AsyncIterator, Dict, List, Optional, TypedDict

import httpx
import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from core_orchestrator.http_client import (
    action_client,
    device_client,
    gateway_client,
    memory_client,
    persona_client,
    voice_client,
)
from core_orchestrator.intent_router import Intent, get_intent_router
from safety_guard import default_guard, safe_fallback_reply
from shared_runtime.config import get_settings
from shared_contracts.models import (
    ActionSequence,
    EmotionState,
    EmotionTag,
    MemoryCategory,
    MemoryRecallResult,
    PersonaProfile,
    RelationshipMetrics,
    TurnContext,
    VoiceSynthesisRequest,
    VoiceTranscriptionResult,
)
from shared.prompt_engine import build_base_system_prompt, build_conversation_system_prompt
from voice_layer.resolver import resolve_profile_id

logger = structlog.get_logger()


def _monolithic_llm_error_hint(exc: BaseException) -> str:
    """Context-aware hint so quota/billing errors are not mistaken for bad API keys."""
    low = str(exc).lower()
    if any(
        token in low
        for token in (
            "403",
            "429",
            "quota",
            "free tier",
            "allocationquota",
            "exhausted",
            "insufficient",
            "billing",
            "balance",
            "欠费",
        )
    ):
        return (
            "本次更像服务商额度或计费限制（例如免费额度用尽）。请到阿里云 DashScope 等控制台开通按量付费，"
            "或关闭「仅使用免费额度 / use free tier only」后再试。"
        )
    return "请检查设置页面中的 API Key、Base URL 和模型名称是否正确。"

# Last assembled conversation system prompt (for /orchestrator/debug/system_prompt).
_DEBUG_SYSTEM_PROMPT_SNAPSHOT: Dict[str, Any] = {}


def record_debug_system_prompt(session_id: str, user_id: str, system_prompt: str) -> None:
    """Store the most recent full system prompt for engineering inspection."""
    from datetime import datetime, timezone

    global _DEBUG_SYSTEM_PROMPT_SNAPSHOT
    _DEBUG_SYSTEM_PROMPT_SNAPSHOT = {
        "session_id": session_id,
        "user_id": user_id,
        "system_prompt": system_prompt,
        "prompt_length": len(system_prompt),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_debug_system_prompt_snapshot() -> Dict[str, Any]:
    if not _DEBUG_SYSTEM_PROMPT_SNAPSHOT:
        return {
            "session_id": None,
            "user_id": None,
            "system_prompt": None,
            "prompt_length": 0,
            "updated_at": None,
            "hint": "先通过主聊天发送一条消息，这里会显示最近一次组装的完整 system prompt（含记忆与 working memory 块）。",
        }
    return dict(_DEBUG_SYSTEM_PROMPT_SNAPSHOT)

_NAME_PATTERN = re.compile(r"我叫([\w\u4e00-\u9fff·]{1,20})")
_PREFERENCE_PATTERN = re.compile(r"我(?:很|最)?喜欢([^，。！？!?]{1,30})")


class OrchestratorState(TypedDict):
    """LangGraph state shared across all nodes."""

    messages: Annotated[List[BaseMessage], add_messages]
    turn_context: Optional[TurnContext]
    intent: Optional[str]
    intent_confidence: Optional[float]
    intent_reasoning: Optional[str]
    intent_entities: Optional[Dict[str, Any]]
    memory_result: Optional[MemoryRecallResult]
    persona_profile: Optional[PersonaProfile]
    emotion_state: Optional[EmotionState]
    relationship_metrics: Optional[RelationshipMetrics]
    assistant_message: Optional[str]
    voice_url: Optional[str]
    voice_duration_ms: Optional[int]
    voice_error: Optional[str]
    action_sequence: Optional[ActionSequence]
    device_command_sent: Optional[bool]
    error: Optional[str]
    skip_voice: Optional[bool]
    skip_action: Optional[bool]


def build_initial_state(turn_context: TurnContext) -> OrchestratorState:
    return OrchestratorState(
        messages=[
            SystemMessage(content=build_base_system_prompt()),
            HumanMessage(content=turn_context.user_message),
        ],
        turn_context=turn_context,
        intent=None,
        intent_confidence=None,
        intent_reasoning=None,
        intent_entities=None,
        memory_result=None,
        persona_profile=None,
        emotion_state=None,
        relationship_metrics=None,
        assistant_message=None,
        voice_url=None,
        voice_duration_ms=None,
        voice_error=None,
        action_sequence=None,
        device_command_sent=False,
        error=None,
        skip_voice=False,
        skip_action=False,
    )


def build_minimal_memory_sync_state(
    turn_context: TurnContext,
    assistant_message: str,
    *,
    emotion_state: Optional[EmotionState] = None,
    relationship_metrics: Optional[RelationshipMetrics] = None,
    intent: Optional[str] = None,
) -> OrchestratorState:
    """Orchestrator-shaped state for memory sync only (no chat messages required)."""
    return OrchestratorState(
        messages=[],
        turn_context=turn_context,
        intent=intent,
        intent_confidence=None,
        intent_reasoning=None,
        intent_entities=None,
        memory_result=None,
        persona_profile=None,
        emotion_state=emotion_state,
        relationship_metrics=relationship_metrics,
        assistant_message=assistant_message,
        voice_url=None,
        voice_duration_ms=None,
        voice_error=None,
        action_sequence=None,
        device_command_sent=False,
        error=None,
        skip_voice=False,
        skip_action=False,
    )


DEFAULT_PERSONA_NAME = "陪伴者"


def _default_persona() -> PersonaProfile:
    return PersonaProfile(name=DEFAULT_PERSONA_NAME)


def _default_memory_result() -> MemoryRecallResult:
    return MemoryRecallResult(entries=[], graph_facts=[])


def _safe_emotion(data: Any = None) -> EmotionState:
    """Safely construct a valid EmotionState from dict or existing state.

    Centralises type validation so callers never need scattered try/except
    around ``EmotionState(**data)``.  If ``data`` is already an
    ``EmotionState`` it is returned unchanged; if it is a ``dict`` we
    attempt ``EmotionState(**data)`` and silently fall back to a neutral
    default on failure; otherwise ``EmotionState()`` is returned.
    """
    if isinstance(data, EmotionState):
        return data
    if isinstance(data, dict):
        try:
            return EmotionState(**data)
        except Exception:
            pass
    return EmotionState()


async def _recall_memory_monolithic(tc: TurnContext, state: OrchestratorState, log: Any) -> OrchestratorState:
    """Direct in-process persona + memory recall for monolithic mode.

    Bypasses /persona/get_profile HTTP which requires request.app.state.* and
    may return 503 if persona_engine lifespan failed to initialise those objects.

    Reads persisted emotion_state and relationship_metrics so the companion's
    personality state evolves across turns instead of resetting to baseline.
    """
    from persona_engine.persona_store import get_persona_profile

    # Read user_profile (if any) to honor role_id preference set by onboarding
    role_id = "default"
    try:
        from user_profile import get_default_store

        snapshot = await get_default_store().get(tc.user.user_id)
        if snapshot and isinstance(snapshot.preferences, dict):
            role_id = snapshot.preferences.get("role_id") or "default"
    except Exception as exc:
        log.warning("user_profile_load_failed", error=str(exc))

    # Persona: read directly from YAML — no HTTP, no app.state dependency
    persona = None
    try:
        persona = get_persona_profile(role_id=role_id)
        state["persona_profile"] = persona
    except Exception as exc:
        log.warning("monolithic_persona_failed", error=str(exc))
        state["persona_profile"] = _default_persona()
        persona = state["persona_profile"]

    # Emotion: try persisted state first, fall back to persona baseline
    try:
        from persona_engine.runtime import get_emotion_engine
        emotion_engine = get_emotion_engine()
        current_emotion = await emotion_engine.get_current_emotion(tc.user.user_id)
        baseline = persona.emotional_baseline if persona else None
        if current_emotion.trigger == "baseline" and baseline:
            state["emotion_state"] = _safe_emotion(baseline)
        else:
            state["emotion_state"] = current_emotion
    except Exception as exc:
        log.warning("emotion_state_load_failed", error=str(exc))
        baseline = persona.emotional_baseline if persona else None
        state["emotion_state"] = _safe_emotion(baseline)

    # Relationship: read persisted metrics from tracker
    try:
        from persona_engine.runtime import get_relationship_tracker
        tracker = get_relationship_tracker()
        state["relationship_metrics"] = await tracker.get_metrics(tc.user.user_id)
    except Exception as exc:
        log.warning("relationship_load_failed", error=str(exc))
        state["relationship_metrics"] = RelationshipMetrics(user_id=tc.user.user_id)

    # Memory: via ASGI transport (memory endpoints use get_db, not request.app.state.*)
    try:
        resp = await memory_client.post(
            "/memory/recall",
            json_payload={
                "query": tc.user_message,
                "user_id": tc.user.user_id,
                "session_id": tc.session_id,
                "top_k": 5,
                "include_graph": True,
            },
        )
        memory_data = resp.json()
        state["memory_result"] = MemoryRecallResult(**memory_data) if memory_data else _default_memory_result()
    except Exception as exc:
        log.warning("monolithic_memory_recall_failed", error=str(exc))
        state["memory_result"] = _default_memory_result()

    log.info(
        "monolithic_memory_recalled",
        memory_entries=len(state["memory_result"].entries),
        persona_name=state["persona_profile"].name,
        emotion_primary=state["emotion_state"].primary.value if state["emotion_state"] else None,
        relationship_intimacy=round(state["relationship_metrics"].intimacy, 3) if state["relationship_metrics"] else 0,
    )
    return state


def _memory_channel_prefix(memory_channel: Optional[str]) -> str:
    if not memory_channel:
        return ""
    return f"【来源：{memory_channel}】\n"


def _build_memory_payloads(
    tc: TurnContext,
    state: OrchestratorState,
    *,
    memory_channel: Optional[str] = None,
) -> List[Dict[str, Any]]:
    assistant_message = (state.get("assistant_message") or "").strip()
    emotion = state.get("emotion_state")
    intent = state.get("intent") or Intent.CHAT.value
    emotion_tags = [emotion.primary.value] if emotion else []
    prefix = _memory_channel_prefix(memory_channel)

    payloads: List[Dict[str, Any]] = [
        {
            "user_id": tc.user.user_id,
            "category": MemoryCategory.EVENT.value,
            "content": prefix + f"用户说：{tc.user_message}\n助手回复：{assistant_message}",
            "importance": 0.55 if intent == Intent.CHAT.value else 0.65,
            "emotion_tags": emotion_tags,
            "source_turn_id": tc.turn_id,
        }
    ]

    if match := _NAME_PATTERN.search(tc.user_message):
        payloads.append(
            {
                "user_id": tc.user.user_id,
                "category": MemoryCategory.FACT.value,
                "content": prefix + f"用户的名字是{match.group(1)}",
                "importance": 0.95,
                "emotion_tags": emotion_tags,
                "source_turn_id": tc.turn_id,
            }
        )

    if match := _PREFERENCE_PATTERN.search(tc.user_message):
        payloads.append(
            {
                "user_id": tc.user.user_id,
                "category": MemoryCategory.PREFERENCE.value,
                "content": prefix + f"用户喜欢{match.group(1).strip()}",
                "importance": 0.9,
                "emotion_tags": emotion_tags,
                "source_turn_id": tc.turn_id,
            }
        )

    return payloads


def _is_monolithic() -> bool:
    """Check if running in monolithic mode (in-process LLM, no HTTP to persona_engine)."""
    settings = get_settings()
    return settings.monolithic or os.environ.get("COMPANION_MONOLITHIC", "false").lower() in ("1", "true", "yes")


def _rule_based_reply(user_message: str, persona_name: str = DEFAULT_PERSONA_NAME) -> str:
    """Rule-based fallback used when no LLM provider is configured."""
    msg = user_message
    if any(tok in msg for tok in ("你叫什么", "你是谁")):
        return f"我是{persona_name}，会一直在这里陪你聊天。"
    if any(tok in msg for tok in ("你好", "嗨", "在吗", "早上好", "晚上好")):
        return f"我在呢，我是{persona_name}！今天你最想先聊哪件事？"
    if any(tok in msg for tok in ("难过", "伤心", "烦", "累", "生气", "焦虑", "崩溃", "压力")):
        return "听起来你现在不太舒服。我先陪着你，你愿意把最难受的那一部分慢慢说给我听吗？"
    if any(tok in msg for tok in ("开心", "高兴", "不错", "太好了", "棒", "哈哈")):
        return "这听起来真的很不错，我也替你开心。你最想分享的是哪一段？"
    if any(tok in msg for tok in ("记得", "还记得", "上次", "之前")):
        return "我会认真记住我们聊过的内容，从这次开始把你说的都放在心里。"
    return "我在认真听你说。你可以继续讲，我会尽量记住对你重要的内容。"


async def _try_action_executor(tc: TurnContext, intent: str) -> Optional[Dict[str, Any]]:
    """If the user message looks like a registered action, run it.

    Returns ``None`` when no action matches — the caller should fall
    back to the normal LLM-driven path. Returns a dict with the
    handler name + ``ActionResult`` fields when the executor handled
    the turn, so the state machine can render the assistant message
    without spending an LLM call.

    Routing rule (deliberately simple, all keyword-based):
      1. The intent_router routed to TOOL_USE.
      2. ``ActionRegistry.find_by_keyword`` matches one of the
         registered handlers' keyword list.
      3. We dispatch with a ``raw_text`` param so handlers like
         ``set_reminder`` can re-parse the natural-language delay.
    """
    if intent != Intent.TOOL_USE.value:
        return None
    try:
        from action_executor import handlers as _handlers  # noqa: F401
        from action_executor.registry import get_registry
    except Exception as exc:
        logger.warning("action_executor.import_failed", error=str(exc))
        return None

    registry = get_registry()
    name = registry.find_by_keyword(tc.user_message)
    if not name:
        return None

    params: Dict[str, Any] = {
        "user_id": tc.user.user_id,
        "session_id": tc.session_id,
        "raw_text": tc.user_message,
    }
    result = await registry.dispatch(name, params)
    return {
        "name": name,
        "ok": result.ok,
        "message": result.message,
        "data": result.data,
        "proactive_push": result.proactive_push,
    }


async def _generate_response_monolithic(tc: TurnContext, system_prompt: str, persona_name: str = DEFAULT_PERSONA_NAME) -> str:
    """Call LLM directly (monolithic mode) without HTTP roundtrip to persona_engine."""
    from shared.llm_client import LLMClient

    llm = LLMClient()
    if llm.has_configured_provider():
        try:
            result = await llm.generate(
                system_prompt=system_prompt,
                user_message=tc.user_message,
                temperature=0.7,
                max_tokens=1024,
            )
            return result["assistant_message"]
        except Exception as exc:
            logger.warning("monolithic_llm_failed", error=str(exc))
            return f"⚠️ LLM 调用失败：{exc}\n\n{_monolithic_llm_error_hint(exc)}"

    return _rule_based_reply(tc.user_message, persona_name)


async def _stream_response_monolithic(
    tc: TurnContext,
    system_prompt: str,
    persona_name: str = DEFAULT_PERSONA_NAME,
) -> AsyncIterator[str]:
    """Streaming variant of ``_generate_response_monolithic``.

    Yields token chunks. When no provider is configured it streams the
    rule-based reply chunk-by-chunk so the SSE pipeline still feels
    incremental on the client side. On provider error it yields a single
    user-facing error message chunk and stops.
    """
    from shared.llm_client import LLMClient, chunk_text_stream

    llm = LLMClient()
    if llm.has_configured_provider():
        try:
            async for token in llm.generate_stream(
                system_prompt=system_prompt,
                user_message=tc.user_message,
                temperature=0.7,
                max_tokens=1024,
            ):
                yield token
            return
        except Exception as exc:
            logger.warning("monolithic_llm_stream_failed", error=str(exc))
            yield f"⚠️ LLM 调用失败：{exc}\n\n{_monolithic_llm_error_hint(exc)}"
            return

    fallback_text = _rule_based_reply(tc.user_message, persona_name)
    async for chunk in chunk_text_stream(fallback_text):
        yield chunk


async def build_prompt_preview(
    tc: TurnContext,
    *,
    intent: Optional[str] = None,
    intent_confidence: Optional[float] = None,
    intent_entities: Optional[Dict[str, Any]] = None,
) -> str:
    """Assemble the same conversation system prompt used at reply time (debug).

    Mirrors the pre-generation path in ``stream_assistant_response`` when
    ``intent`` is not injected: classify intent → recall memory →
    ``build_conversation_system_prompt``. Optional ``intent*`` overrides skip
    classification for deterministic tests.
    """
    state: OrchestratorState = build_initial_state(tc)
    if intent is not None:
        state["intent"] = intent
        state["intent_confidence"] = intent_confidence
        state["intent_entities"] = intent_entities or {}
    else:
        state = await node_classify_intent(state)
    if state.get("error"):
        return build_base_system_prompt()
    state = await node_recall_memory(state)
    if state.get("error"):
        return build_base_system_prompt()

    persona = state.get("persona_profile") or _default_persona()
    memory = state.get("memory_result")
    emotion = state.get("emotion_state")
    relationship = state.get("relationship_metrics")
    system_prompt = build_conversation_system_prompt(
        persona=persona,
        emotion=emotion,
        relationship=relationship,
        memory=memory,
    )
    settings = get_settings()
    if settings.enable_voice:
        system_prompt += (
            "\n\n【能力说明】你支持语音播报。"
            "当用户希望你“说一句”“念出来”或“用语音回复”时，不要声称自己无法发声；"
            "直接正常给出要说的内容，系统会按需合成语音。"
        )
    return system_prompt


_NEGATIVE_TOKENS = (
    "难过",
    "伤心",
    "烦",
    "好累",
    "生气",
    "焦虑",
    "害怕",
    "崩溃",
    "讨厌",
    "失眠",
    "孤独",
    "压力",
    "郁闷",
    "委屈",
    "想哭",
    "受不了",
    "没意思",
    "好烦",
    "烦死了",
    "低落",
    "沮丧",
    "失望",
)
_USER_DISTRESS = ("好累", "想哭", "受不了", "绝望", "撑不住", "好难", "扛不住", "心里堵")
_POSITIVE_TOKENS = (
    "开心",
    "高兴",
    "喜欢",
    "爱",
    "谢谢",
    "太好了",
    "不错",
    "棒",
    "期待",
    "哈哈",
    "幸福",
    "耶",
    "超爱",
    "舒服",
    "满足",
    "惊喜",
    "感动",
)
_USER_SURPRISED = ("居然", "真的假的", "天哪", "没想到", "这么神奇", "哇塞")
_USER_ANGRY = ("气死", "气炸了", "讨厌", "混蛋", "烦死了", "恨", "凭什么")

_ASSISTANT_WARM = ("抱抱", "陪着你", "一直在", "心疼", "摸摸头", "乖", "有我在", "不孤单")
_ASSISTANT_HAPPY = ("哈哈", "太好啦", "真开心", "替你高兴", "棒极了", "真棒", "庆祝", "耶")
_ASSISTANT_CONCERN = ("别担心", "没事的", "会好的", "慢慢来", "我在听", "不怪你", "别太累")
_ASSISTANT_SURPRISED = ("真的吗", "居然", "没想到", "哇", "这么厉害", "原来如此")
_ASSISTANT_APOLOGY = ("对不起", "抱歉", "是我不好", "让你久等")


def _emotion_from_user_message(msg: str) -> Optional[EmotionState]:
    """How the companion should feel when empathizing with the user's text."""
    if not msg or not msg.strip():
        return None
    low = msg.lower()
    if any(tok in msg for tok in _USER_DISTRESS):
        return EmotionState(
            primary=EmotionTag.CONCERNED,
            intensity=0.68,
            valence=-0.12,
            arousal=0.48,
            trigger="user_distress",
        )
    if any(tok in msg for tok in _USER_ANGRY):
        return EmotionState(
            primary=EmotionTag.CONCERNED,
            intensity=0.62,
            valence=-0.18,
            arousal=0.52,
            trigger="user_angry",
        )
    if any(tok in msg for tok in _NEGATIVE_TOKENS):
        return EmotionState(
            primary=EmotionTag.SAD,
            intensity=0.58,
            valence=-0.38,
            arousal=0.42,
            trigger="user_negative",
        )
    if any(tok in msg for tok in _POSITIVE_TOKENS):
        return EmotionState(
            primary=EmotionTag.HAPPY,
            intensity=0.72,
            valence=0.58,
            arousal=0.52,
            trigger="user_positive",
        )
    if any(tok in msg for tok in _USER_SURPRISED):
        return EmotionState(
            primary=EmotionTag.SURPRISED,
            intensity=0.55,
            valence=0.18,
            arousal=0.62,
            trigger="user_surprise",
        )
    if any(w in low for w in ("sad", "depressed", "anxious", "tired of", "hate ", "angry")):
        return EmotionState(
            primary=EmotionTag.CONCERNED,
            intensity=0.6,
            valence=-0.22,
            arousal=0.48,
            trigger="user_en_negative",
        )
    if any(w in low for w in ("happy", "love you", "great", "thanks", "excited")):
        return EmotionState(
            primary=EmotionTag.HAPPY,
            intensity=0.65,
            valence=0.55,
            arousal=0.5,
            trigger="user_en_positive",
        )
    return None


def _emotion_from_assistant_reply(reply: str) -> Optional[EmotionState]:
    """Infer companion mood from her own reply (warmth / surprise / concern)."""
    if not reply or len(reply.strip()) < 2:
        return None
    if any(tok in reply for tok in _ASSISTANT_APOLOGY):
        return EmotionState(
            primary=EmotionTag.SAD,
            intensity=0.48,
            valence=-0.12,
            arousal=0.36,
            trigger="reply_apology",
        )
    if any(tok in reply for tok in _ASSISTANT_SURPRISED):
        return EmotionState(
            primary=EmotionTag.SURPRISED,
            intensity=0.52,
            valence=0.12,
            arousal=0.58,
            trigger="reply_surprise",
        )
    if any(tok in reply for tok in _ASSISTANT_WARM):
        return EmotionState(
            primary=EmotionTag.AFFECTIONATE,
            intensity=0.62,
            valence=0.48,
            arousal=0.42,
            trigger="reply_warm",
        )
    if any(tok in reply for tok in _ASSISTANT_CONCERN):
        return EmotionState(
            primary=EmotionTag.CONCERNED,
            intensity=0.58,
            valence=0.05,
            arousal=0.4,
            trigger="reply_concern",
        )
    if any(tok in reply for tok in _ASSISTANT_HAPPY):
        return EmotionState(
            primary=EmotionTag.HAPPY,
            intensity=0.64,
            valence=0.52,
            arousal=0.54,
            trigger="reply_happy",
        )
    return None


def _derive_emotion(
    user_message: str,
    assistant_message: str,
    current: Optional[EmotionState],
) -> EmotionState:
    """Update companion emotion from user empathy, then from assistant reply tone, then baseline.

    Order: user sentiment wins for empathy; otherwise use cues from the model's reply so the
    UI moves off a permanent ``calm`` when the character uses warm or lively language.
    """
    user_hit = _emotion_from_user_message(user_message)
    if user_hit is not None:
        return user_hit
    asst_hit = _emotion_from_assistant_reply(assistant_message)
    if asst_hit is not None:
        return asst_hit
    um = user_message or ""
    if "？" in um or "?" in um:
        return EmotionState(
            primary=EmotionTag.CALM,
            intensity=0.52,
            valence=0.28,
            arousal=0.46,
            trigger="user_question",
        )
    return current or EmotionState(primary=EmotionTag.CALM, intensity=0.4, valence=0.3, arousal=0.3)


async def node_receive(state: OrchestratorState) -> OrchestratorState:
    """Receive and validate turn context. Handle voice transcription if needed."""
    tc = state["turn_context"]
    if tc is None:
        state["error"] = "Missing turn_context"
        return state

    log = logger.bind(turn_id=tc.turn_id, session_id=tc.session_id)
    log.info(
        "state_machine_receive",
        user_id=tc.user.user_id,
        has_voice=tc.has_voice,
        request_voice_reply=tc.request_voice_reply,
    )

    if tc.has_voice and tc.user_message.strip() == "":
        try:
            resp = await voice_client.post(
                "/voice/transcribe",
                json_payload={
                    "turn_id": tc.turn_id,
                    "user_id": tc.user.user_id,
                    "language": tc.user.language,
                },
            )
            transcription = VoiceTranscriptionResult(**resp.json())
            tc.user_message = transcription.text
            state["messages"] = [
                SystemMessage(content=build_base_system_prompt()),
                HumanMessage(content=tc.user_message),
            ]
            log.info("voice_transcribed", text=tc.user_message, confidence=transcription.confidence)
        except Exception as exc:
            log.error("voice_transcription_failed", error=str(exc))
            state["error"] = f"Voice transcription failed: {exc}"

    # Safety: input pre-check (BLOCK 时直接短路, 绕过 LLM)
    if not state.get("error") and tc.user_message:
        verdict = default_guard.check_input(tc.user_message)
        if verdict.blocked:
            fallback = safe_fallback_reply(verdict.reason)
            state["assistant_message"] = fallback
            state["messages"] = state["messages"] + [AIMessage(content=fallback)]
            state["skip_voice"] = False
            state["skip_action"] = True
            state["intent"] = Intent.CHAT.value
            state["intent_confidence"] = 0.0
            log.warning(
                "input_blocked_by_safety_guard",
                matched=verdict.matched_terms,
                reason=verdict.reason,
            )
        elif verdict.warned:
            log.info(
                "input_safety_warn",
                matched=verdict.matched_terms,
                pii=verdict.pii_hits,
            )

    return state


async def node_classify_intent(state: OrchestratorState) -> OrchestratorState:
    tc = state["turn_context"]
    if tc is None or state.get("error") or state.get("assistant_message"):
        return state

    log = logger.bind(turn_id=tc.turn_id)
    result = await get_intent_router().classify(tc.user_message)

    state["intent"] = result.intent.value
    state["intent_confidence"] = result.confidence
    state["intent_reasoning"] = result.reasoning
    state["intent_entities"] = result.entities
    log.info("intent_classified", intent=result.intent.value, confidence=result.confidence)
    return state


async def node_recall_memory(state: OrchestratorState) -> OrchestratorState:
    tc = state["turn_context"]
    if tc is None or state.get("error") or state.get("assistant_message"):
        return state

    log = logger.bind(turn_id=tc.turn_id)

    # Monolithic mode: bypass /persona/get_profile which requires request.app.state.*
    if _is_monolithic():
        return await _recall_memory_monolithic(tc, state, log)

    async def _fetch_persona() -> Dict[str, Any]:
        try:
            resp = await persona_client.post("/persona/get_profile", json_payload={"user_id": tc.user.user_id})
            return resp.json()
        except Exception as exc:
            log.warning("persona_fetch_failed", error=str(exc))
            return {}

    async def _fetch_memory() -> Dict[str, Any]:
        try:
            resp = await memory_client.post(
                "/memory/recall",
                json_payload={
                    "query": tc.user_message,
                    "user_id": tc.user.user_id,
                    "session_id": tc.session_id,
                    "top_k": 5,
                    "include_graph": True,
                },
            )
            return resp.json()
        except Exception as exc:
            log.warning("memory_recall_failed", error=str(exc))
            return {}

    persona_data, memory_data = await asyncio.gather(_fetch_persona(), _fetch_memory())

    persona_raw = persona_data.get("persona") if isinstance(persona_data.get("persona"), dict) else persona_data
    try:
        state["persona_profile"] = PersonaProfile(**persona_raw) if persona_raw else _default_persona()
    except Exception:
        state["persona_profile"] = _default_persona()

    emotion_raw = None
    if isinstance(persona_data.get("emotion"), dict):
        emotion_raw = persona_data["emotion"]
    elif persona_raw and isinstance(persona_raw.get("emotional_baseline"), dict):
        emotion_raw = persona_raw["emotional_baseline"]
    state["emotion_state"] = _safe_emotion(emotion_raw)

    relationship_raw = None
    if isinstance(persona_data.get("relationship"), dict):
        relationship_raw = persona_data["relationship"]
    elif isinstance(persona_data.get("relationship_metrics"), dict):
        relationship_raw = persona_data["relationship_metrics"]
    try:
        state["relationship_metrics"] = (
            RelationshipMetrics(**relationship_raw)
            if relationship_raw
            else RelationshipMetrics(user_id=tc.user.user_id)
        )
    except Exception:
        state["relationship_metrics"] = RelationshipMetrics(user_id=tc.user.user_id)

    try:
        state["memory_result"] = MemoryRecallResult(**memory_data) if memory_data else _default_memory_result()
    except Exception:
        state["memory_result"] = _default_memory_result()

    log.info(
        "memory_recalled",
        memory_entries=len(state["memory_result"].entries),
        persona_name=state["persona_profile"].name,
    )
    return state


async def node_generate_response(state: OrchestratorState) -> OrchestratorState:
    tc = state["turn_context"]
    if tc is None or state.get("error") or state.get("assistant_message"):
        return state

    log = logger.bind(turn_id=tc.turn_id)
    intent = state.get("intent") or Intent.CHAT.value
    settings = get_settings()

    persona = state.get("persona_profile")
    memory = state.get("memory_result")
    emotion = state.get("emotion_state")
    relationship = state.get("relationship_metrics")
    system_prompt = build_conversation_system_prompt(
        persona=persona,
        emotion=emotion,
        relationship=relationship,
        memory=memory,
    )
    if settings.enable_voice:
        system_prompt += (
            "\n\n【能力说明】你支持语音播报。"
            "当用户希望你“说一句”“念出来”或“用语音回复”时，不要声称自己无法发声；"
            "直接正常给出要说的内容，系统会按需合成语音。"
        )
    record_debug_system_prompt(tc.session_id, tc.user.user_id, system_prompt)
    messages: List[BaseMessage] = [SystemMessage(content=system_prompt)]
    for msg in state["messages"]:
        if not isinstance(msg, SystemMessage):
            messages.append(msg)

    if intent == Intent.DEVICE_COMMAND.value and settings.enable_device_coordination:
        try:
            entities = state.get("intent_entities") or {}
            command = entities.get("command", tc.user_message)
            resp = await device_client.post(
                "/device/send_command",
                json_payload={"user_id": tc.user.user_id, "command": command, "payload": entities},
            )
            assistant_msg = resp.json().get("message", "指令已经发送。")
            state["device_command_sent"] = True
            state["assistant_message"] = assistant_msg
            state["messages"] = messages + [AIMessage(content=assistant_msg)]
            state["emotion_state"] = _derive_emotion(
                tc.user_message, assistant_msg, state.get("emotion_state")
            )
            log.info("device_command_handled", command=command)
            return state
        except Exception as exc:
            log.warning("device_command_failed", error=str(exc))
            state["assistant_message"] = "设备指令发送失败了，你可以稍后再试一次。"
            state["messages"] = messages + [AIMessage(content=state["assistant_message"])]
            state["emotion_state"] = _derive_emotion(
                tc.user_message, state["assistant_message"], state.get("emotion_state")
            )
            return state

    action_handled = await _try_action_executor(tc, intent)
    if action_handled is not None and action_handled.get("ok"):
        assistant_msg = action_handled.get("message") or "好的。"
        state["assistant_message"] = assistant_msg
        state["messages"] = messages + [AIMessage(content=assistant_msg)]
        state["emotion_state"] = _derive_emotion(
            tc.user_message, assistant_msg, state.get("emotion_state")
        )
        log.info("action_executor_handled", name=action_handled.get("name"))
        return state

    # Monolithic mode: call LLM/fallback directly, skip HTTP to persona_engine
    if _is_monolithic():
        persona_name = (state.get("persona_profile") or _default_persona()).name
        assistant_msg = await _generate_response_monolithic(tc, system_prompt, persona_name)
        state["assistant_message"] = assistant_msg
        state["messages"] = messages + [AIMessage(content=assistant_msg)]
        state["emotion_state"] = _derive_emotion(
            tc.user_message, assistant_msg, state.get("emotion_state")
        )
        log.info("monolithic_response_generated", length=len(assistant_msg))
        return state

    emotion_from_persona_api = False
    try:
        resp = await persona_client.post(
            "/persona/generate_response",
            json_payload={
                "user_id": tc.user.user_id,
                "session_id": tc.session_id,
                "user_message": tc.user_message,
                "system_prompt": system_prompt,
                "emotion": emotion.model_dump(mode="json") if emotion else None,
                "relationship": relationship.model_dump(mode="json") if relationship else None,
            },
        )
        data = resp.json()
        assistant_msg = data.get("assistant_message", "...")
        new_emotion_raw = data.get("new_emotion")
        if isinstance(new_emotion_raw, dict):
            state["emotion_state"] = _safe_emotion(new_emotion_raw)
            emotion_from_persona_api = True
    except Exception as exc:
        log.warning("persona_generate_failed", error=str(exc))
        assistant_msg = "我在呢，你继续说，我会认真听。"

    state["assistant_message"] = assistant_msg
    state["messages"] = messages + [AIMessage(content=assistant_msg)]
    if not emotion_from_persona_api:
        state["emotion_state"] = _derive_emotion(
            tc.user_message, assistant_msg, state.get("emotion_state")
        )
    log.info("response_generated", intent=intent, length=len(assistant_msg))
    return state


async def node_synthesize_voice(state: OrchestratorState) -> OrchestratorState:
    tc = state["turn_context"]
    if tc is None or state.get("error"):
        return state

    wants_voice = bool(tc.request_voice_reply or tc.has_voice)
    settings = get_settings()

    if not settings.enable_voice:
        state["skip_voice"] = True
        state["voice_url"] = None
        state["voice_duration_ms"] = None
        state["voice_error"] = "voice module disabled" if wants_voice else None
        logger.bind(turn_id=tc.turn_id).info(
            "voice_synthesize_skipped",
            reason="enable_voice_false",
            wants_voice=wants_voice,
            voice_error=state["voice_error"],
        )
        return state

    if not wants_voice:
        state["skip_voice"] = True
        state["voice_url"] = None
        state["voice_duration_ms"] = None
        state["voice_error"] = None
        logger.bind(turn_id=tc.turn_id).info("voice_synthesize_skipped", reason="no_voice_flags")
        return state

    state["voice_url"] = None
    state["voice_duration_ms"] = None
    state["voice_error"] = None

    log = logger.bind(turn_id=tc.turn_id)
    assistant_msg = state.get("assistant_message") or ""
    emotion = state.get("emotion_state")

    persona = state.get("persona_profile")
    voice_profile_id = resolve_profile_id(
        raw_voice_preference=persona.voice_preference if persona else None,
        persona_id=persona.persona_id if persona else None,
    )

    req = VoiceSynthesisRequest(
        text=assistant_msg,
        voice_id=voice_profile_id,
        emotion=emotion.primary if emotion else EmotionTag.NEUTRAL,
        language=tc.user.language,
    )

    log.info(
        "voice_synthesize_begin",
        text_len=len(assistant_msg),
        has_voice=tc.has_voice,
        request_voice_reply=tc.request_voice_reply,
        voice_duration_ms_user=tc.voice_duration_ms,
    )

    try:
        resp = await voice_client.post("/voice/synthesize", json_payload=req.model_dump())
        data = resp.json()
        url = data.get("voice_url") or data.get("audio_url")
        if isinstance(url, str):
            url = url.strip() or None
        if not url:
            state["voice_url"] = None
            state["voice_duration_ms"] = None
            state["voice_error"] = (
                f"TTS returned empty audio URL (HTTP {resp.status_code}). Body keys: {list(data.keys())}"
            )
            log.warning("voice_synthesis_empty_url", status=resp.status_code, keys=list(data.keys()))
            return state

        state["voice_url"] = url
        raw_dur = data.get("duration_ms")
        if raw_dur is not None:
            try:
                state["voice_duration_ms"] = int(raw_dur)
            except (TypeError, ValueError):
                state["voice_duration_ms"] = None
        state["voice_error"] = None
        log.info(
            "voice_synthesized",
            voice_url=state["voice_url"],
            voice_duration_ms=state["voice_duration_ms"],
        )
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or "")[:1200]
        err_msg = f"/voice/synthesize HTTP {exc.response.status_code}: {body or exc.response.reason_phrase}"
        with contextlib.suppress(Exception):
            j = exc.response.json()
            detail = j.get("detail")
            if isinstance(detail, dict) and detail.get("message"):
                err_msg = f"/voice/synthesize HTTP {exc.response.status_code}: {detail['message']}"
            elif isinstance(detail, str):
                err_msg = f"/voice/synthesize HTTP {exc.response.status_code}: {detail}"
        state["voice_url"] = None
        state["voice_duration_ms"] = None
        state["voice_error"] = err_msg
        log.warning(
            "voice_synthesis_failed_http",
            status=exc.response.status_code,
            body_preview=body[:400],
        )
    except Exception as exc:
        err_msg = str(exc)
        state["voice_url"] = None
        state["voice_duration_ms"] = None
        state["voice_error"] = err_msg
        log.warning("voice_synthesis_failed", error=err_msg)

    return state


async def node_generate_action(state: OrchestratorState) -> OrchestratorState:
    tc = state["turn_context"]
    if tc is None or state.get("error"):
        return state

    settings = get_settings()
    if not settings.enable_action_2d:
        state["skip_action"] = True
        return state

    log = logger.bind(turn_id=tc.turn_id)
    emotion = state.get("emotion_state")
    try:
        resp = await action_client.post(
            "/action/generate",
            json_payload={
                "turn_id": tc.turn_id,
                "user_id": tc.user.user_id,
                "assistant_message": state.get("assistant_message") or "",
                "emotion": emotion.primary.value if emotion else EmotionTag.NEUTRAL.value,
                "reference_image_url": settings.avatar_2d_reference_url,
            },
        )
        state["action_sequence"] = ActionSequence(**resp.json())
        log.info("action_generated", frames=len(state["action_sequence"].frames))
    except Exception as exc:
        log.warning("action_generation_failed", error=str(exc))
        state["action_sequence"] = None

    return state


async def node_send_response(state: OrchestratorState) -> OrchestratorState:
    tc = state["turn_context"]
    if tc is None or state.get("error"):
        return state

    # Safety: output post-check (BLOCK 时替换为兜底文案)
    assistant_msg = state.get("assistant_message") or ""
    if assistant_msg:
        verdict = default_guard.check_output(assistant_msg)
        if verdict.blocked:
            log = logger.bind(turn_id=tc.turn_id)
            log.warning(
                "output_blocked_by_safety_guard",
                matched=verdict.matched_terms,
                reason=verdict.reason,
            )
            fallback = safe_fallback_reply(verdict.reason)
            state["assistant_message"] = fallback
            new_msgs = [m for m in state["messages"] if not isinstance(m, AIMessage)]
            state["messages"] = new_msgs + [AIMessage(content=fallback)]

    # In monolithic mode the frontend reads the response directly from the
    # orchestrator HTTP response — no gateway push needed.
    if _is_monolithic():
        return state

    log = logger.bind(turn_id=tc.turn_id)
    try:
        resp = await gateway_client.post(
            "/gateway/send",
            json_payload={
                "user_id": tc.user.user_id,
                "platform": tc.platform.value,
                "content": state.get("assistant_message") or "",
                "voice_url": state.get("voice_url"),
                "action_sequence": state["action_sequence"].model_dump() if state.get("action_sequence") else None,
                "reply_to_message_id": None,
            },
        )
        log.info("response_sent", message_id=resp.json().get("message_id"))
    except Exception as exc:
        log.error("response_send_failed", error=str(exc))
        state["error"] = f"Failed to send response: {exc}"

    return state


async def sync_completed_turn_to_memory(
    *,
    turn_context: TurnContext,
    orchestration_state: OrchestratorState,
    memory_channel: Optional[str] = None,
) -> None:
    """Persist working memory, persona deltas, and long-term memory for one completed turn.

    Shared by the LangGraph ``sync_memory`` node and realtime voice (async hook).
    """
    tc = turn_context
    state = orchestration_state
    if not (tc.user_message or "").strip():
        return

    log = logger.bind(turn_id=tc.turn_id)
    assistant_msg = state.get("assistant_message") or ""
    emotion = state.get("emotion_state")
    relationship = state.get("relationship_metrics")

    # Working memory is layer-1 short-term context; we ALWAYS observe a
    # turn into it (even when the rich pipeline is disabled), because
    # this is what feeds the next turn's prompt's "【当前对话状态】"
    # section. Failing to record working memory degrades to "amnesia
    # between turns" — much more visible than missing long-term storage.
    try:
        from memory_system.working import get_working_memory

        wm = get_working_memory()
        await wm.observe_turn(
            session_id=tc.session_id,
            turn_id=tc.turn_id,
            user_message=tc.user_message,
            assistant_message=assistant_msg,
            emotion=emotion.primary.value if emotion else None,
            intent=state.get("intent"),
        )
    except Exception as exc:
        log.warning("working_memory.observe_failed", error=str(exc))

    # --- Personality state persistence (emotion + relationship) ---------
    # Write current emotion back so the next turn starts from where we left off
    if _is_monolithic():
        try:
            from persona_engine.runtime import get_emotion_engine

            engine = get_emotion_engine()
            # Determine sentiment for relationship tracking
            emotion_valence = emotion.valence if emotion else 0
            if emotion_valence > 0.2:
                sentiment = "positive"
            elif emotion_valence < -0.15:
                sentiment = "negative"
            else:
                sentiment = "neutral"

            # Detect disclosure / shared experience from message content
            has_disclosure = bool(_NAME_PATTERN.search(tc.user_message)) or any(
                tok in tc.user_message for tok in ("其实", "说实话", "秘密", "只告诉你", "我有个")
            )
            shared_experience = any(
                tok in tc.user_message for tok in ("一起", "我们也", "我们都", "还记得那次")
            )

            # Persist emotion
            await engine.transition_from_user_message(
                tc.user.user_id,
                sentiment=sentiment,
                relationship=relationship or RelationshipMetrics(user_id=tc.user.user_id),
                message_content=tc.user_message,
            )
            log.info("emotion_state_persisted", sentiment=sentiment)

            # Persist relationship
            from persona_engine.runtime import get_relationship_tracker

            tracker = get_relationship_tracker()
            await tracker.record_interaction(
                tc.user.user_id,
                sentiment=sentiment,
                has_disclosure=has_disclosure,
                is_routine=False,
                shared_experience=shared_experience,
            )
            log.info("relationship_persisted", sentiment=sentiment)
        except Exception as exc:
            log.warning("personality_state_persist_failed", error=str(exc))

    # --- User profile updates (discovered facts) ------------------------
    if _is_monolithic():
        try:
            from user_profile import get_default_store

            profile_store = get_default_store()

            if match := _NAME_PATTERN.search(tc.user_message):
                discovered_name = match.group(1)
                await profile_store.merge_preferences(tc.user.user_id, nickname=discovered_name)
                log.info("user_profile_name_discovered", name=discovered_name)

            if match := _PREFERENCE_PATTERN.search(tc.user_message):
                discovered_pref = match.group(1).strip()
                await profile_store.merge_preferences(
                    tc.user.user_id,
                    latest_like=discovered_pref,
                )
                log.info("user_profile_preference_discovered", preference=discovered_pref)
        except Exception as exc:
            log.warning("user_profile_update_failed", error=str(exc))

    # --- Long-term memory pipeline ---------------------------------------
    if not get_settings().enable_memory_pipeline:
        log.info("memory_synced")
        return

    # Heuristic stash — fast, runs even without LLM key
    for payload in _build_memory_payloads(tc, state, memory_channel=memory_channel):
        try:
            await memory_client.post("/memory/store", json_payload=payload)
        except Exception as exc:
            log.warning("memory_sync_failed", error=str(exc), category=payload.get("category"))

    # Rich extraction pipeline — runs in-process in monolithic mode (no Celery)
    if _is_monolithic():
        import asyncio as _asyncio

        pipe_meta: Dict[str, Any] = {"intent": state.get("intent")}
        if memory_channel:
            pipe_meta["source_channel"] = memory_channel

        async def _bg_pipeline() -> None:
            try:
                from memory_system.pipeline import run_pipeline_async

                pipe_emotion = state.get("emotion_state")
                await run_pipeline_async(
                    {
                        "turn_id": tc.turn_id,
                        "user_id": tc.user.user_id,
                        "user_message": tc.user_message,
                        "assistant_message": assistant_msg,
                        "emotion": pipe_emotion.primary.value if pipe_emotion else None,
                        "metadata": pipe_meta,
                    }
                )
            except Exception as exc:
                log.warning("pipeline_async_failed", error=str(exc))

        # Fire-and-forget: don't block the user response on pipeline cost.
        _asyncio.create_task(_bg_pipeline())

    log.info("memory_synced")


async def node_sync_memory(state: OrchestratorState) -> OrchestratorState:
    tc = state["turn_context"]
    if tc is None:
        return state

    await sync_completed_turn_to_memory(
        turn_context=tc,
        orchestration_state=state,
        memory_channel=None,
    )
    return state


def _should_continue(state: OrchestratorState) -> str:
    if state.get("error"):
        return "end"
    return "continue"


def build_graph() -> StateGraph:
    """Build and return the compiled LangGraph state machine."""
    graph = StateGraph(OrchestratorState)

    graph.add_node("receive", node_receive)
    graph.add_node("classify_intent", node_classify_intent)
    graph.add_node("recall_memory", node_recall_memory)
    graph.add_node("generate_response", node_generate_response)
    graph.add_node("synthesize_voice", node_synthesize_voice)
    graph.add_node("generate_action", node_generate_action)
    graph.add_node("send_response", node_send_response)
    graph.add_node("sync_memory", node_sync_memory)

    graph.set_entry_point("receive")
    graph.add_conditional_edges("receive", _should_continue, {"continue": "classify_intent", "end": "sync_memory"})
    graph.add_conditional_edges("classify_intent", _should_continue, {"continue": "recall_memory", "end": "sync_memory"})
    graph.add_conditional_edges("recall_memory", _should_continue, {"continue": "generate_response", "end": "sync_memory"})
    graph.add_conditional_edges("generate_response", _should_continue, {"continue": "synthesize_voice", "end": "sync_memory"})
    graph.add_conditional_edges("synthesize_voice", _should_continue, {"continue": "generate_action", "end": "sync_memory"})
    graph.add_conditional_edges("generate_action", _should_continue, {"continue": "send_response", "end": "sync_memory"})
    graph.add_conditional_edges("send_response", _should_continue, {"continue": "sync_memory", "end": "sync_memory"})
    graph.add_edge("sync_memory", END)

    return graph.compile()


_compiled_graph: Any = None


def get_compiled_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


# ---------------------------------------------------------------------------
# Streaming variant: same node pipeline, but exposes incremental LLM tokens.
# Used by /orchestrator/turn/stream (SSE).
# ---------------------------------------------------------------------------


async def stream_assistant_response(tc: TurnContext) -> AsyncIterator[Dict[str, Any]]:
    """Run the full conversation pipeline but stream the LLM step.

    Event shapes:
      ``{"event": "meta", "intent": str|None, "intent_confidence": float|None,
         "emotion": dict|None, "memory_entries_count": int}``
      ``{"event": "token", "text": str}``
      ``{"event": "done", "_state": OrchestratorState}``
      ``{"event": "error", "error": str}``

    The orchestrator is responsible for converting ``done`` into the
    user-facing payload (``assistant_message`` / ``emotion`` / ``voice_url`` /
    ``action_sequence`` / etc.) — this lets ``Orchestrator`` keep its single
    success-result builder.
    """
    settings = get_settings()
    state: OrchestratorState = build_initial_state(tc)

    # Pre-generate nodes (receive → classify_intent → recall_memory)
    state = await node_receive(state)
    if state.get("error"):
        yield {"event": "error", "error": state["error"]}
        yield {"event": "done", "_state": state}
        return

    state = await node_classify_intent(state)
    if state.get("error"):
        yield {"event": "error", "error": state["error"]}
        yield {"event": "done", "_state": state}
        return

    state = await node_recall_memory(state)
    if state.get("error"):
        yield {"event": "error", "error": state["error"]}
        yield {"event": "done", "_state": state}
        return

    memory_result = state.get("memory_result")
    memory_count = (
        len(memory_result.entries) if memory_result and hasattr(memory_result, "entries") else 0
    )
    pre_emotion = state.get("emotion_state")
    yield {
        "event": "meta",
        "intent": state.get("intent"),
        "intent_confidence": state.get("intent_confidence"),
        "emotion": pre_emotion.model_dump(mode="json") if pre_emotion else None,
        "memory_entries_count": memory_count,
    }

    # Generate (streaming)
    persona = state.get("persona_profile") or _default_persona()
    memory = state.get("memory_result")
    emotion = state.get("emotion_state")
    relationship = state.get("relationship_metrics")
    system_prompt = build_conversation_system_prompt(
        persona=persona,
        emotion=emotion,
        relationship=relationship,
        memory=memory,
    )
    if settings.enable_voice:
        system_prompt += (
            "\n\n【能力说明】你支持语音播报。"
            "当用户希望你“说一句”“念出来”或“用语音回复”时，不要声称自己无法发声；"
            "直接正常给出要说的内容，系统会按需合成语音。"
        )
    record_debug_system_prompt(tc.session_id, tc.user.user_id, system_prompt)

    intent = state.get("intent") or Intent.CHAT.value

    # Device-command intents short-circuit the LLM entirely (same logic as
    # node_generate_response). We still emit the device response as a single
    # token so the UI can render it like a streamed reply.
    if intent == Intent.DEVICE_COMMAND.value and settings.enable_device_coordination:
        try:
            entities = state.get("intent_entities") or {}
            command = entities.get("command", tc.user_message)
            resp = await device_client.post(
                "/device/send_command",
                json_payload={"user_id": tc.user.user_id, "command": command, "payload": entities},
            )
            assistant_msg = resp.json().get("message", "指令已经发送。")
            state["device_command_sent"] = True
        except Exception as exc:
            logger.warning("stream.device_command_failed", error=str(exc))
            assistant_msg = "设备指令发送失败了，你可以稍后再试一次。"

        if assistant_msg:
            yield {"event": "token", "text": assistant_msg}
        state["assistant_message"] = assistant_msg
        state["messages"] = list(state["messages"]) + [AIMessage(content=assistant_msg)]
        state["emotion_state"] = _derive_emotion(
            tc.user_message, assistant_msg, state.get("emotion_state")
        )
    elif (action_handled := await _try_action_executor(tc, intent)) and action_handled.get("ok"):
        # Action executor handled it (set_reminder / get_time / ...). Stream
        # the deterministic reply through chunk_text_stream so the UI gets
        # the same token-by-token feel as an LLM reply.
        from shared.llm_client import chunk_text_stream

        assistant_msg = action_handled.get("message") or "好的。"
        accumulated: List[str] = []
        async for chunk in chunk_text_stream(assistant_msg):
            accumulated.append(chunk)
            yield {"event": "token", "text": chunk}
        full = "".join(accumulated) or assistant_msg
        state["assistant_message"] = full
        state["messages"] = list(state["messages"]) + [AIMessage(content=full)]
        state["emotion_state"] = _derive_emotion(tc.user_message, full, state.get("emotion_state"))
        logger.info("stream.action_executor_handled", name=action_handled.get("name"))
    else:
        accumulated: List[str] = []
        emotion_from_persona_api = False
        try:
            if _is_monolithic():
                persona_name = persona.name if persona else DEFAULT_PERSONA_NAME
                async for token in _stream_response_monolithic(tc, system_prompt, persona_name):
                    accumulated.append(token)
                    yield {"event": "token", "text": token}
            else:
                # Microservice mode: try persona_engine streaming first, fall
                # back to non-streaming HTTP if persona_engine doesn't expose
                # a streaming endpoint.
                try:
                    async for token in _stream_via_persona_engine(
                        tc, system_prompt, emotion, relationship
                    ):
                        accumulated.append(token)
                        yield {"event": "token", "text": token}
                except Exception as exc:
                    logger.warning("stream.persona_stream_unavailable", error=str(exc))
                    try:
                        resp = await persona_client.post(
                            "/persona/generate_response",
                            json_payload={
                                "user_id": tc.user.user_id,
                                "session_id": tc.session_id,
                                "user_message": tc.user_message,
                                "system_prompt": system_prompt,
                                "emotion": emotion.model_dump(mode="json") if emotion else None,
                                "relationship": relationship.model_dump(mode="json") if relationship else None,
                            },
                        )
                        data = resp.json()
                        assistant_msg = data.get("assistant_message", "...")
                        from shared.llm_client import chunk_text_stream

                        async for chunk in chunk_text_stream(assistant_msg):
                            accumulated.append(chunk)
                            yield {"event": "token", "text": chunk}
                        new_emotion_raw = data.get("new_emotion")
                        if isinstance(new_emotion_raw, dict):
                            state["emotion_state"] = _safe_emotion(new_emotion_raw)
                            emotion_from_persona_api = True
                    except Exception as inner_exc:
                        logger.warning("stream.persona_generate_failed", error=str(inner_exc))
                        accumulated.append("我在呢，你继续说，我会认真听。")
                        yield {"event": "token", "text": accumulated[-1]}
        except Exception as exc:
            logger.exception("stream.generate_failed", error=str(exc))
            err_msg = f"⚠️ LLM 调用失败：{exc}"
            accumulated.append(err_msg)
            yield {"event": "token", "text": err_msg}

        assistant_msg = "".join(accumulated)
        state["assistant_message"] = assistant_msg
        state["messages"] = list(state["messages"]) + [AIMessage(content=assistant_msg)]

        if _is_monolithic():
            state["emotion_state"] = _derive_emotion(
                tc.user_message, assistant_msg, state.get("emotion_state")
            )
        elif not emotion_from_persona_api:
            state["emotion_state"] = _derive_emotion(
                tc.user_message, assistant_msg, state.get("emotion_state")
            )

    # Post-generate nodes (voice / action / send / memory sync) — same as
    # the non-streaming graph. Failures here only add to state["error"] and
    # never block the already-streamed assistant message.
    state = await node_synthesize_voice(state)
    state = await node_generate_action(state)
    state = await node_send_response(state)
    state = await node_sync_memory(state)

    yield {"event": "done", "_state": state}


async def _stream_via_persona_engine(
    tc: TurnContext,
    system_prompt: str,
    emotion: Optional[EmotionState],
    relationship: Optional[RelationshipMetrics],
) -> AsyncIterator[str]:
    """Reserved for a future ``/persona/generate_response_stream`` endpoint.

    The microservice persona engine does not yet expose an SSE endpoint,
    so this raises ``NotImplementedError`` to trigger the non-streaming
    fallback path in ``stream_assistant_response``. Defined here so the
    streaming code path is symmetric with the monolithic case and easy
    to extend without changing call sites.
    """
    raise NotImplementedError("persona_engine streaming not yet wired")
    if False:  # pragma: no cover - keep the function shape async-iterator
        yield ""
