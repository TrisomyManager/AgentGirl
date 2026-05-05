"""LangGraph state machine for the conversation flow."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Annotated, Any, AsyncIterator, Dict, List, Optional, TypedDict

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
from shared.config import get_settings
from shared.models import (
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

logger = structlog.get_logger()

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
        action_sequence=None,
        device_command_sent=False,
        error=None,
        skip_voice=False,
        skip_action=False,
    )


def _default_persona() -> PersonaProfile:
    return PersonaProfile(name="小暖")


def _default_memory_result() -> MemoryRecallResult:
    return MemoryRecallResult(entries=[], graph_facts=[])


async def _recall_memory_monolithic(tc: TurnContext, state: OrchestratorState, log: Any) -> OrchestratorState:
    """Direct in-process persona + memory recall for monolithic mode.

    Bypasses /persona/get_profile HTTP which requires request.app.state.* and
    may return 503 if persona_engine lifespan failed to initialise those objects.
    """
    from persona_engine.persona_store import get_persona_profile

    # Persona: read directly from soul.yaml — no HTTP, no app.state dependency
    try:
        persona = get_persona_profile()
        state["persona_profile"] = persona
        baseline = persona.emotional_baseline
        try:
            state["emotion_state"] = EmotionState(**baseline) if baseline else EmotionState()
        except Exception:
            state["emotion_state"] = EmotionState()
    except Exception as exc:
        log.warning("monolithic_persona_failed", error=str(exc))
        state["persona_profile"] = _default_persona()
        state["emotion_state"] = EmotionState()

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
    )
    return state


def _build_memory_payloads(tc: TurnContext, state: OrchestratorState) -> List[Dict[str, Any]]:
    assistant_message = (state.get("assistant_message") or "").strip()
    emotion = state.get("emotion_state")
    intent = state.get("intent") or Intent.CHAT.value
    emotion_tags = [emotion.primary.value] if emotion else []

    payloads: List[Dict[str, Any]] = [
        {
            "user_id": tc.user.user_id,
            "category": MemoryCategory.EVENT.value,
            "content": f"用户说：{tc.user_message}\n助手回复：{assistant_message}",
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
                "content": f"用户的名字是{match.group(1)}",
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
                "content": f"用户喜欢{match.group(1).strip()}",
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


def _rule_based_reply(user_message: str, persona_name: str = "小暖") -> str:
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


async def _generate_response_monolithic(tc: TurnContext, system_prompt: str, persona_name: str = "小暖") -> str:
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
            return f"⚠️ LLM 调用失败：{exc}\n\n请检查设置页面中的 API Key、Base URL 和模型名称是否正确。"

    return _rule_based_reply(tc.user_message, persona_name)


async def _stream_response_monolithic(
    tc: TurnContext,
    system_prompt: str,
    persona_name: str = "小暖",
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
            yield f"⚠️ LLM 调用失败：{exc}\n\n请检查设置页面中的 API Key、Base URL 和模型名称是否正确。"
            return

    fallback_text = _rule_based_reply(tc.user_message, persona_name)
    async for chunk in chunk_text_stream(fallback_text):
        yield chunk


_NEGATIVE_TOKENS = ("难过", "伤心", "烦", "累", "生气", "焦虑", "害怕", "崩溃", "讨厌", "失眠", "孤独", "压力")
_POSITIVE_TOKENS = ("开心", "高兴", "喜欢", "爱", "谢谢", "太好了", "不错", "棒", "期待", "哈哈", "幸福")


def _derive_emotion(user_message: str, current: Optional[EmotionState]) -> EmotionState:
    """Infer an updated emotion state from the user's message sentiment."""
    msg = user_message
    if any(tok in msg for tok in _NEGATIVE_TOKENS):
        return EmotionState(primary=EmotionTag.SAD, intensity=0.6, valence=-0.4, arousal=0.4)
    if any(tok in msg for tok in _POSITIVE_TOKENS):
        return EmotionState(primary=EmotionTag.HAPPY, intensity=0.7, valence=0.6, arousal=0.5)
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

    return state


async def node_classify_intent(state: OrchestratorState) -> OrchestratorState:
    tc = state["turn_context"]
    if tc is None or state.get("error"):
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
    if tc is None or state.get("error"):
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
    try:
        state["emotion_state"] = EmotionState(**emotion_raw) if emotion_raw else EmotionState()
    except Exception:
        state["emotion_state"] = EmotionState()

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
    if tc is None or state.get("error"):
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
            log.info("device_command_handled", command=command)
            return state
        except Exception as exc:
            log.warning("device_command_failed", error=str(exc))
            state["assistant_message"] = "设备指令发送失败了，你可以稍后再试一次。"
            state["messages"] = messages + [AIMessage(content=state["assistant_message"])]
            return state

    # Monolithic mode: call LLM/fallback directly, skip HTTP to persona_engine
    if _is_monolithic():
        persona_name = (state.get("persona_profile") or _default_persona()).name
        assistant_msg = await _generate_response_monolithic(tc, system_prompt, persona_name)
        state["assistant_message"] = assistant_msg
        state["messages"] = messages + [AIMessage(content=assistant_msg)]
        state["emotion_state"] = _derive_emotion(tc.user_message, state.get("emotion_state"))
        log.info("monolithic_response_generated", length=len(assistant_msg))
        return state

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
            try:
                state["emotion_state"] = EmotionState(**new_emotion_raw)
            except Exception:
                pass
    except Exception as exc:
        log.warning("persona_generate_failed", error=str(exc))
        assistant_msg = "我在呢，你继续说，我会认真听。"

    state["assistant_message"] = assistant_msg
    state["messages"] = messages + [AIMessage(content=assistant_msg)]
    log.info("response_generated", intent=intent, length=len(assistant_msg))
    return state


async def node_synthesize_voice(state: OrchestratorState) -> OrchestratorState:
    tc = state["turn_context"]
    if tc is None or state.get("error"):
        return state

    settings = get_settings()
    if not settings.enable_voice:
        state["skip_voice"] = True
        return state
    if not (tc.request_voice_reply or tc.has_voice):
        state["skip_voice"] = True
        return state

    log = logger.bind(turn_id=tc.turn_id)
    assistant_msg = state.get("assistant_message") or ""
    emotion = state.get("emotion_state")
    voice_id = state["persona_profile"].voice_preference if state.get("persona_profile") else None

    req = VoiceSynthesisRequest(
        text=assistant_msg,
        voice_id=voice_id,
        emotion=emotion.primary if emotion else EmotionTag.NEUTRAL,
        language=tc.user.language,
    )

    try:
        resp = await voice_client.post("/voice/synthesize", json_payload=req.model_dump())
        state["voice_url"] = resp.json().get("voice_url")
        log.info("voice_synthesized", voice_url=state["voice_url"])
    except Exception as exc:
        log.warning("voice_synthesis_failed", error=str(exc))
        state["voice_url"] = None

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


async def node_sync_memory(state: OrchestratorState) -> OrchestratorState:
    tc = state["turn_context"]
    if tc is None:
        return state

    if not get_settings().enable_memory_pipeline:
        return state

    log = logger.bind(turn_id=tc.turn_id)

    # Heuristic stash — fast, runs even without LLM key
    for payload in _build_memory_payloads(tc, state):
        try:
            await memory_client.post("/memory/store", json_payload=payload)
        except Exception as exc:
            log.warning("memory_sync_failed", error=str(exc), category=payload.get("category"))

    # Rich extraction pipeline — runs in-process in monolithic mode (no Celery)
    if _is_monolithic():
        import asyncio as _asyncio

        async def _bg_pipeline() -> None:
            try:
                from memory_system.pipeline import run_pipeline_async
                emotion = state.get("emotion_state")
                await run_pipeline_async(
                    {
                        "turn_id": tc.turn_id,
                        "user_id": tc.user.user_id,
                        "user_message": tc.user_message,
                        "assistant_message": state.get("assistant_message") or "",
                        "emotion": emotion.primary.value if emotion else None,
                        "metadata": {"intent": state.get("intent")},
                    }
                )
            except Exception as exc:
                log.warning("pipeline_async_failed", error=str(exc))

        # Fire-and-forget: don't block the user response on pipeline cost.
        _asyncio.create_task(_bg_pipeline())

    log.info("memory_synced")
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
    else:
        accumulated: List[str] = []
        try:
            if _is_monolithic():
                persona_name = persona.name if persona else "小暖"
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
                            try:
                                state["emotion_state"] = EmotionState(**new_emotion_raw)
                            except Exception:
                                pass
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
            state["emotion_state"] = _derive_emotion(tc.user_message, state.get("emotion_state"))

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
