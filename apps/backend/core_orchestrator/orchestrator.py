"""Main orchestration logic that coordinates all modules via HTTP and Redis events."""

from __future__ import annotations

import os
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

import structlog
from langchain_core.messages import AIMessage, SystemMessage

from shared_runtime.config import get_settings
from shared_contracts.events import TurnEndEvent
from shared_contracts.models import EmotionTag, TurnContext

from core_orchestrator.event_bus import EventBus, get_event_bus
from core_orchestrator.http_client import check_all_services
from core_orchestrator.state_machine import (
    OrchestratorState,
    build_initial_state,
    get_compiled_graph,
    stream_assistant_response,
)

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Proactive turn helpers
# ---------------------------------------------------------------------------

_PROACTIVE_SYSTEM_INSTRUCTIONS = """【主动发起对话】
你现在正在主动发起一次对话。不需要等待用户先说话，请直接根据以下触发原因和你们的对话历史，用温暖自然的口吻开启对话。

请严格遵循以下原则：
- 绝对不要提及这是由"系统"、"程序"、"定时器"或"自动"触发的
- 说1-3句话，简洁自然，像朋友突然想起对方一样
- 根据你们的关系亲密度调整语气——越亲密越随意
- 如果触发原因是记忆关怀，自然地把你记得的事融入对话，当作你主动想起的
- 不要用疑问句堆砌——可以分享你的感受，也可以温和地陈述"""

_TRIGGER_USER_PROMPTS = {
    "idle_checkin": (
        "用户已经 {hours_inactive:.1f} 小时没有联系你了。"
        "请主动问候，表达你的关心和想念。语气温柔，不要责备。"
    ),
    "morning_greeting": (
        "现在是早晨（当地时间 {local_hour} 点左右）。"
        "请用温暖愉快的语气向用户道早安，可以简单问一下对方今天的计划或心情。"
    ),
    "evening_greeting": (
        "现在是傍晚（当地时间 {local_hour} 点左右）。"
        "关心一下用户今天过得怎么样，用温柔体贴的语气，像在一天结束时陪在对方身边。"
    ),
    "memory_followup": (
        "你记得用户之前提过这件事：{memory_content}。"
        "请自然地提起这件事，表达你的关心和你在意对方说过的话。"
        "不要生硬地说'我记得你说过'——而是像朋友自然地想起一样。"
    ),
}

_DEFAULT_USER_PROMPT = (
    "请主动发起一次对话。用温暖自然的口吻，像朋友突然想起对方一样。"
)


def _build_proactive_instructions(
    trigger_type: str, trigger_context: Dict[str, Any]
) -> str:
    """Assemble the system + user prompt block for proactive message generation."""
    user_prompt_template = _TRIGGER_USER_PROMPTS.get(
        trigger_type, _DEFAULT_USER_PROMPT
    )
    try:
        user_prompt = user_prompt_template.format(**trigger_context)
    except KeyError:
        user_prompt = user_prompt_template

    return _PROACTIVE_SYSTEM_INSTRUCTIONS + "\n\n" + user_prompt


def tc_dict_id(tc: TurnContext) -> str:
    """Tiny helper exposed for the streaming code path."""
    return tc.turn_id


class Orchestrator:
    """High-level orchestrator that runs the LangGraph state machine per turn."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._event_bus: Optional[EventBus] = None
        self._graph: Any = None

    async def startup(self) -> None:
        logger.info("orchestrator_startup_begin")
        self._event_bus = await get_event_bus()
        self._graph = get_compiled_graph()

        if not self.settings.lite_mode:
            redis_ok = await self._event_bus.ping()
            if not redis_ok:
                logger.error("orchestrator_redis_unavailable")
                raise RuntimeError("Redis is unreachable at startup")
            logger.info("orchestrator_redis_ok")
        else:
            logger.info("orchestrator_lite_mode_skip_redis_check")

        if os.environ.get("COMPANION_MONOLITHIC", "false").lower() in ("1", "true", "yes"):
            logger.info("orchestrator_monolithic_skip_service_health")
        else:
            service_health = await check_all_services()
            for svc in service_health:
                status = "ok" if svc["healthy"] else "unreachable"
                logger.info("orchestrator_service_health", service=svc["service"], status=status)

        logger.info("orchestrator_startup_complete")

    async def shutdown(self) -> None:
        logger.info("orchestrator_shutdown_begin")
        from core_orchestrator.http_client import close_all

        await close_all()
        logger.info("orchestrator_shutdown_complete")

    async def process_turn(self, turn_context: TurnContext) -> Dict[str, Any]:
        """Process a single user turn end-to-end through the state machine."""
        log = logger.bind(turn_id=turn_context.turn_id, session_id=turn_context.session_id)
        log.info(
            "process_turn_start",
            user_id=turn_context.user.user_id,
            platform=turn_context.platform.value,
            has_voice=turn_context.has_voice,
        )

        initial_state = build_initial_state(turn_context)

        try:
            final_state = await self._graph.ainvoke(initial_state)
        except Exception as exc:
            log.exception("process_turn_graph_error", error=str(exc))
            return self._build_error_result(turn_context, str(exc))

        result = self._build_success_result(turn_context, final_state)
        await self._publish_turn_end(turn_context, final_state, result)
        log.info("process_turn_complete", assistant_length=len(result.get("assistant_message", "")))
        return result

    async def process_turn_stream(
        self,
        turn_context: TurnContext,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream a turn as a sequence of structured events.

        Event shapes (consumed by ``/orchestrator/turn/stream``):
          - ``{"event": "meta",  "intent": ..., "emotion": ..., "memory_entries_count": N}``
          - ``{"event": "token", "text": "..."}``
          - ``{"event": "done",  "assistant_message": "...", "voice_url": ..., "emotion": ..., "action_sequence": ..., "turn_id": ..., "session_id": ..., "user_id": ...}``
          - ``{"event": "error", "error": "..."}``

        Token order matches LLM emission order. ``meta`` is fired once
        intent classification + memory recall have run and before the first
        token. ``done`` is fired after voice / action / memory sync.
        """
        log = logger.bind(turn_id=turn_context.turn_id, session_id=turn_context.session_id)
        log.info(
            "process_turn_stream_start",
            user_id=turn_context.user.user_id,
            platform=turn_context.platform.value,
        )

        try:
            async for event in stream_assistant_response(turn_context):
                if event.get("event") == "done":
                    state = event.pop("_state", None)
                    if state is not None:
                        result = self._build_success_result(turn_context, state)
                        await self._publish_turn_end(turn_context, state, result)
                        event.update(
                            {
                                "assistant_message": result["assistant_message"],
                                "emotion": result["emotion"],
                                "voice_url": result["voice_url"],
                                "voice_duration_ms": result.get("voice_duration_ms"),
                                "voice_error": result.get("voice_error"),
                                "action_sequence": result["action_sequence"],
                                "intent": result["intent"],
                                "intent_confidence": result["intent_confidence"],
                                "memory_entries_count": result["memory_entries_count"],
                                "turn_id": tc_dict_id(turn_context),
                                "session_id": turn_context.session_id,
                                "user_id": turn_context.user.user_id,
                            }
                        )
                yield event
        except Exception as exc:
            log.exception("process_turn_stream_error", error=str(exc))
            yield {"event": "error", "error": str(exc)}
            yield {
                "event": "done",
                **self._build_error_result(turn_context, str(exc)),
            }
            return

        log.info("process_turn_stream_complete")

    def _build_success_result(self, tc: TurnContext, state: Dict[str, Any]) -> Dict[str, Any]:
        emotion = state.get("emotion_state")
        action_seq = state.get("action_sequence")
        memory_result = state.get("memory_result")

        if hasattr(memory_result, "entries"):
            memory_entries_count = len(memory_result.entries)
        elif isinstance(memory_result, dict):
            memory_entries_count = len(memory_result.get("entries", []))
        else:
            memory_entries_count = 0

        return {
            "turn_id": tc.turn_id,
            "session_id": tc.session_id,
            "user_id": tc.user.user_id,
            "assistant_message": state.get("assistant_message") or "",
            "emotion": emotion.model_dump() if emotion else None,
            "voice_url": state.get("voice_url"),
            "voice_duration_ms": state.get("voice_duration_ms"),
            "voice_error": state.get("voice_error"),
            "action_sequence": action_seq.model_dump() if action_seq else None,
            "intent": state.get("intent"),
            "intent_confidence": state.get("intent_confidence"),
            "memory_entries_count": memory_entries_count,
            "error": state.get("error"),
        }

    def _build_error_result(self, tc: TurnContext, error: str) -> Dict[str, Any]:
        return {
            "turn_id": tc.turn_id,
            "session_id": tc.session_id,
            "user_id": tc.user.user_id,
            "assistant_message": "抱歉，我刚刚有点卡住了。你可以再说一次，我会继续陪着你。",
            "emotion": None,
            "voice_url": None,
            "voice_duration_ms": None,
            "voice_error": None,
            "action_sequence": None,
            "intent": None,
            "intent_confidence": None,
            "memory_entries_count": 0,
            "error": error,
        }

    async def _publish_turn_end(
        self,
        tc: TurnContext,
        state: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        if self._event_bus is None:
            return

        emotion = state.get("emotion_state")
        action_seq = state.get("action_sequence")
        event = TurnEndEvent(
            event_id=str(uuid.uuid4()),
            source_module="core_orchestrator",
            turn_id=tc.turn_id,
            session_id=tc.session_id,
            user_id=tc.user.user_id,
            assistant_message=result.get("assistant_message", ""),
            emotion=emotion.primary if emotion else EmotionTag.NEUTRAL,
            action_sequence=action_seq,
            voice_url=result.get("voice_url"),
            memory_entries_created=[],
            relationship_delta=state.get("relationship_metrics"),
        )
        try:
            await self._event_bus.publish(event)
        except Exception as exc:
            logger.warning("turn_end_publish_failed", error=str(exc))

    async def generate_proactive_turn(
        self,
        user_id: str,
        session_id: str,
        trigger_type: str,
        trigger_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate a proactive AI-initiated message without a real user turn.

        This bypasses the full LangGraph pipeline and calls the monolithic
        recall → prompt → LLM → sync path directly.  No voice, no actions,
        no intent classification — just a warm, contextual check-in.

        Returns a dict with ``assistant_message``, ``emotion``,
        ``trigger_type``, and ``session_id``.
        """
        import structlog
        _log = structlog.get_logger(__name__).bind(
            user_id=user_id,
            trigger_type=trigger_type,
        )

        from core_orchestrator.state_machine import (
            OrchestratorState,
            _recall_memory_monolithic,
            _generate_response_monolithic,
            sync_completed_turn_to_memory,
        )
        from shared_contracts.models import (
            EmotionState,
            Platform,
            TurnContext,
            UserProfile,
        )
        from shared_runtime.prompt_engine import build_conversation_system_prompt

        # 1. Build a synthetic TurnContext and minimal OrchestratorState
        turn_id = str(uuid.uuid4())
        tc = TurnContext(
            turn_id=turn_id,
            session_id=session_id,
            user=UserProfile(user_id=user_id, platform=Platform.APP),
            user_message=f"[PROACTIVE:{trigger_type}]",
            platform=Platform.APP,
        )

        state: OrchestratorState = {
            "messages": [],
            "turn_context": tc,
            "intent": None,
            "intent_confidence": None,
            "intent_reasoning": None,
            "intent_entities": None,
            "memory_result": None,
            "persona_profile": None,
            "emotion_state": None,
            "relationship_metrics": None,
            "assistant_message": None,
            "voice_url": None,
            "voice_duration_ms": None,
            "voice_error": None,
            "action_sequence": None,
            "device_command_sent": None,
            "error": None,
            "skip_voice": True,
            "skip_action": True,
        }

        # 2. Hydrate persona / emotion / relationship / memory in-process
        try:
            state = await _recall_memory_monolithic(tc, state, _log)
        except Exception as exc:
            _log.warning("proactive_recall_failed", error=str(exc))

        # 3. Build the system prompt with proactive framing
        base_prompt = build_conversation_system_prompt(
            persona=state.get("persona_profile"),
            emotion=state.get("emotion_state"),
            relationship=state.get("relationship_metrics"),
            memory=state.get("memory_result"),
        )
        proactive_instructions = _build_proactive_instructions(trigger_type, trigger_context)
        system_prompt = base_prompt + "\n\n" + proactive_instructions

        persona_name = (
            state["persona_profile"].name
            if state.get("persona_profile")
            else "小暖"
        )

        # 4. Generate via LLM
        try:
            assistant_msg = await _generate_response_monolithic(
                tc, system_prompt, persona_name
            )
        except Exception as exc:
            _log.exception("proactive_generate_failed", error=str(exc))
            return {
                "assistant_message": "",
                "emotion": None,
                "trigger_type": trigger_type,
                "session_id": session_id,
            }

        state["assistant_message"] = assistant_msg

        # 5. Sync memory (so proactive messages are part of conversation history)
        try:
            await sync_completed_turn_to_memory(
                turn_context=tc,
                orchestration_state=state,
            )
        except Exception as exc:
            _log.warning("proactive_sync_memory_failed", error=str(exc))

        emotion = state.get("emotion_state")
        return {
            "assistant_message": assistant_msg,
            "emotion": emotion.model_dump() if emotion else None,
            "trigger_type": trigger_type,
            "session_id": session_id,
        }

    async def service_status(self) -> List[Dict[str, Any]]:
        """Return health status for all downstream services."""
        return await check_all_services()


_orchestrator: Optional[Orchestrator] = None


async def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
        await _orchestrator.startup()
    return _orchestrator


async def shutdown_orchestrator() -> None:
    global _orchestrator
    if _orchestrator is not None:
        await _orchestrator.shutdown()
        _orchestrator = None
