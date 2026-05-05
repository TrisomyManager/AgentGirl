"""Main orchestration logic that coordinates all modules via HTTP and Redis events."""

from __future__ import annotations

import os
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

import structlog
from langchain_core.messages import AIMessage, SystemMessage

from shared.config import get_settings
from shared.events import TurnEndEvent
from shared.models import EmotionTag, TurnContext

from core_orchestrator.event_bus import EventBus, get_event_bus
from core_orchestrator.http_client import check_all_services
from core_orchestrator.state_machine import (
    OrchestratorState,
    build_initial_state,
    get_compiled_graph,
    stream_assistant_response,
)

logger = structlog.get_logger()


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
