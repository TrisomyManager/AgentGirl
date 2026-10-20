"""Owned, ordered background persistence for completed realtime voice turns."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from shared_runtime.user_lifecycle import user_operation

logger = structlog.get_logger("voice_layer.realtime_memory_sync")

# Stable channel tag for long-term / pipeline metadata (align with product wording).
REALTIME_MEMORY_CHANNEL = "voice_call"
_handler: Callable[..., Awaitable[Any]] | None = None
_pending: set[asyncio.Task] = set()
_owners: dict[asyncio.Task, tuple[str, str]] = {}


def set_memory_sync_handler(handler: Callable[..., Awaitable[Any]] | None) -> None:
    """Configure persistence in the host, leaving voice_layer independently usable."""
    global _handler
    _handler = handler


async def drain_memory_sync(*, user_id: str | None = None, session_id: str | None = None) -> None:
    tasks = [task for task in tuple(_pending)
             if (user_id is None or _owners.get(task, (None, None))[0] == user_id)
             and (session_id is None or _owners.get(task, (None, None))[1] == session_id)]
    if tasks:
        # A disconnected reader must not cancel an earlier completed turn's write.
        await asyncio.wait(tasks)


def schedule_realtime_turn_memory_sync(
    *,
    user_id: str,
    session_id: str,
    user_message: str,
    assistant_message: str,
    memory_channel: str = REALTIME_MEMORY_CHANNEL,
    turn_id: str | None = None,
    conversation_context: Any = None,
    content_filtered: bool = False,
) -> None:
    """Queue a background task; never raises to callers."""
    text_u = (user_message or "").strip()
    text_a = (assistant_message or "").strip()
    handler = _handler
    if not text_u or not text_a or handler is None:
        return
    predecessors = [task for task in tuple(_pending) if _owners.get(task) == (user_id, session_id)]

    async def _run() -> None:
        async with user_operation(user_id):
            await _write()

    async def _write() -> None:
        try:
            if predecessors:
                await asyncio.wait(predecessors)
            extra = {}
            if turn_id is not None:
                extra["turn_id"] = turn_id
            if conversation_context is not None:
                extra["conversation_context"] = conversation_context
            if content_filtered:
                extra["content_filtered"] = True
            await handler(
                user_id=user_id,
                session_id=session_id,
                user_message=text_u,
                assistant_message=text_a,
                memory_channel=memory_channel,
                **extra,
            )
        except Exception as exc:
            logger.warning("realtime_memory_sync_failed", error=str(exc))

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_run())
    _pending.add(task)
    _owners[task] = (user_id, session_id)

    def completed(done):
        _pending.discard(done)
        _owners.pop(done, None)

    task.add_done_callback(completed)
