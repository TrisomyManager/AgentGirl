"""FastAPI router for the action executor.

Endpoints:

  GET  /actions/list                — registered handlers + their metadata.
  POST /actions/dispatch            — manually invoke a handler (debug).
  GET  /actions/reminders/{user_id} — list pending reminders for a user.
  POST /actions/reminders           — create a reminder explicitly.
  DELETE /actions/reminders/{id}    — cancel a reminder.
  GET  /actions/push                — SSE stream of proactive push events.
  GET  /actions/push/poll           — Poll events since seq (SSE fallback for buffered proxies).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Import handlers module so BUILTIN_ACTIONS register themselves at import time.
from action_executor import handlers  # noqa: F401
from action_executor.push_bus import get_proactive_push_bus
from action_executor.registry import get_registry
from action_executor.reminders import get_reminders_store

logger = structlog.get_logger("action_executor.api")

router = APIRouter(prefix="/actions", tags=["actions"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class DispatchRequest(BaseModel):
    name: str = Field(..., description="Registered action name")
    params: Dict[str, Any] = Field(default_factory=dict)


class DispatchResponse(BaseModel):
    ok: bool
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)
    proactive_push: Optional[Dict[str, Any]] = None


class CreateReminderRequest(BaseModel):
    user_id: str
    text: str
    fire_at: Optional[str] = Field(
        default=None, description="ISO 8601; if omitted, delay_seconds is required"
    )
    delay_seconds: Optional[int] = Field(default=None, ge=1)
    session_id: Optional[str] = None


class ReminderResponse(BaseModel):
    id: str
    user_id: str
    session_id: Optional[str]
    text: str
    fire_at: str
    created_at: str
    fired_at: Optional[str]
    cancelled_at: Optional[str]
    status: str
    repeat_interval_seconds: Optional[int] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/list")
async def list_actions() -> List[Dict[str, Any]]:
    """List all registered action handlers and their metadata."""
    return get_registry().list_actions()


@router.post("/dispatch", response_model=DispatchResponse)
async def dispatch_action(req: DispatchRequest) -> DispatchResponse:
    """Manually run an action; useful for debugging from the panel."""
    result = await get_registry().dispatch(req.name, req.params)
    return DispatchResponse(
        ok=result.ok,
        message=result.message,
        data=result.data,
        proactive_push=result.proactive_push,
    )


@router.get("/reminders/{user_id}")
async def list_reminders_endpoint(
    user_id: str,
    include_fired: bool = Query(default=False),
    include_cancelled: bool = Query(default=False),
) -> List[ReminderResponse]:
    items = await get_reminders_store().list_for_user(
        user_id=user_id,
        include_fired=include_fired,
        include_cancelled=include_cancelled,
    )
    return [ReminderResponse(**r.to_dict()) for r in items]


@router.post("/reminders", response_model=ReminderResponse)
async def create_reminder(req: CreateReminderRequest) -> ReminderResponse:
    from datetime import datetime, timedelta, timezone

    fire_at = None
    if req.fire_at:
        try:
            parsed = datetime.fromisoformat(req.fire_at)
            fire_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid fire_at: {exc}")
    elif req.delay_seconds:
        fire_at = datetime.now(timezone.utc) + timedelta(seconds=req.delay_seconds)
    else:
        raise HTTPException(
            status_code=400, detail="either fire_at or delay_seconds is required"
        )

    reminder = await get_reminders_store().add(
        user_id=req.user_id,
        text=req.text,
        fire_at=fire_at,
        session_id=req.session_id,
    )
    return ReminderResponse(**reminder.to_dict())


@router.delete("/reminders/{reminder_id}")
async def cancel_reminder_endpoint(
    reminder_id: str,
    user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    ok = await get_reminders_store().cancel(reminder_id, user_id=user_id)
    return {"cancelled": ok, "reminder_id": reminder_id}


@router.get("/push")
async def push_stream() -> StreamingResponse:
    """SSE stream of proactive push events.

    The frontend long-lives one of these per tab. Events use the same
    text/event-stream wire format as ``/orchestrator/turn/stream``::

        event: reminder_fired
        data: {"id": "...", "text": "...", "fire_at": "..."}

    A 2-second heartbeat keeps the connection unbuffered through
    Cloudflare / nginx — without it, intermediaries often hold the
    initial ``event: hello`` frame waiting for more bytes and the
    real ``reminder_fired`` event lands many seconds late.
    """
    bus = get_proactive_push_bus()
    heartbeat_seconds = 2.0

    async def _gen() -> AsyncIterator[bytes]:
        # Send a hello frame immediately so client / proxies open the stream.
        # Pad it with a 2KB SSE comment so reverse proxies that still buffer
        # the first response fragment hit their flush threshold immediately.
        comment_padding = b": " + b" " * 4096 + b"\n"
        yield comment_padding + b"event: hello\ndata: {}\n\n"

        loop = asyncio.get_running_loop()
        subscriber = bus.subscribe().__aiter__()
        next_event_task: asyncio.Task[Any] = loop.create_task(subscriber.__anext__())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        asyncio.shield(next_event_task), timeout=heartbeat_seconds
                    )
                except asyncio.TimeoutError:
                    # Keep the connection warm so Cloudflare / nginx don't buffer.
                    yield b"event: ping\ndata: {}\n\n"
                    continue
                payload = json.dumps(event.payload, ensure_ascii=False, default=str)
                yield f"event: {event.kind}\ndata: {payload}\n\n".encode("utf-8")
                next_event_task = loop.create_task(subscriber.__anext__())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("push_stream.error", error=str(exc))
        finally:
            if not next_event_task.done():
                next_event_task.cancel()
            try:
                await subscriber.aclose()  # type: ignore[attr-defined]
            except Exception:
                pass

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/push/poll")
async def push_poll(
    since: int = Query(0, ge=0, description="Last seen event seq from a prior poll or 0"),
) -> Dict[str, Any]:
    """Long-poll friendly snapshot of proactive events after ``since``.

    Use when ``GET /actions/push`` SSE is buffered by Cloudflare / nginx and
    the browser never receives the first bytes in time.
    """
    return await get_proactive_push_bus().poll_since(since)
