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
import uuid
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
from action_executor.proactive_preferences import CarePreferences, care_preferences_store
from action_executor.task_agent import task_agent
from action_executor.task_store import task_store
from action_executor.tool_catalog import ToolContext
from action_executor.task_policy import task_tool_scope

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


class TaskRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    request: str = Field(min_length=1, max_length=10000)
    turn_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1, max_length=128)


class ResumeTaskRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    clarification: str = Field(min_length=1, max_length=2000)


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


@router.get("/capabilities")
async def list_capabilities() -> Dict[str, Any]:
    """User-facing capabilities catalogue — what Xiaonuan can do for you."""
    from action_executor.capabilities import build_capabilities
    return {"capabilities": build_capabilities()}


@router.get("/user_state")
async def get_user_state(
    user_id: str = Query(default="user_001", description="Target user id"),
) -> Dict[str, Any]:
    """What Xiaonuan is currently doing for this user.

    Returns upcoming reminders, recently completed/cancelled items,
    proactive care rules, and open tasks.
    """
    from action_executor.user_state import build_user_state
    return await build_user_state(user_id)


@router.get("/list")
async def list_actions() -> List[Dict[str, Any]]:
    """List all registered action handlers and their metadata."""
    return get_registry().list_actions()


@router.get("/plugins")
async def list_plugins():
    from action_executor.plugins import plugin_manager

    return {"plugins": plugin_manager.status()}


class CatalogInstallRequest(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.get("/plugins/catalog")
async def get_plugin_catalog():
    from action_executor.plugin_catalog import catalog_status
    from action_executor.plugins import plugin_manager
    from shared_runtime.config import get_settings

    return catalog_status(plugin_manager, enabled=get_settings().plugin_install_enabled)


@router.post("/plugins/catalog/{identifier}/install", status_code=201)
async def install_plugin(identifier: str, request: CatalogInstallRequest):
    from action_executor.plugin_catalog import CatalogError, install_catalog_plugin
    from action_executor.plugins import plugin_manager
    from shared_runtime.config import get_settings

    try:
        return await install_catalog_plugin(
            plugin_manager, identifier, request.sha256, enabled=get_settings().plugin_install_enabled
        )
    except CatalogError as error:
        raise HTTPException(error.status, detail=error.message) from None


@router.get("/mcp/tools")
async def list_mcp_tools():
    return {"tools": get_registry().mcp_tools()}


@router.get("/tasks")
async def list_tasks(user_id: str = Query(min_length=1, max_length=128)):
    return {"tasks": await task_store.list_for_user(user_id)}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, user_id: str = Query(min_length=1, max_length=128)):
    run = await task_store.get(task_id, user_id)
    if run is None:
        raise HTTPException(404, detail="Task not found")
    return run


@router.post("/tasks")
async def execute_task(req: TaskRequest):
    context = ToolContext(req.user_id, req.session_id, req.turn_id, req.request)
    tools = await task_agent.catalog.tools_for(context)
    result = await task_agent.execute(context, allowed_tools=task_tool_scope(req.request, tools))
    return {"ok": result.ok, "message": result.message, **result.data}


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str, req: ResumeTaskRequest):
    run = await task_store.get(task_id, req.user_id)
    if run is None:
        raise HTTPException(404, detail="Task not found")
    if run["status"] != "awaiting_input":
        raise HTTPException(409, detail="Task is not awaiting input")
    full_request = run["request"] + "\n用户补充：" + req.clarification
    context = ToolContext(req.user_id, run["session_id"], run["turn_id"], req.clarification)
    tools = await task_agent.catalog.tools_for(context)
    result = await task_agent.execute(context, allowed_tools=task_tool_scope(full_request, tools), resume_run_id=task_id)
    return {"ok": result.ok, "message": result.message, **result.data}


@router.delete("/tasks/{task_id}")
async def cancel_task(task_id: str, user_id: str = Query(min_length=1, max_length=128)):
    if await task_store.get(task_id, user_id) is None:
        raise HTTPException(404, detail="Task not found")
    return {"cancelled": await task_agent.cancel(task_id, user_id)}


@router.get("/proactive/preferences/{user_id}", response_model=CarePreferences)
async def get_care_preferences(user_id: str) -> CarePreferences:
    return await care_preferences_store.get(user_id)


@router.put("/proactive/preferences/{user_id}", response_model=CarePreferences)
async def save_care_preferences(user_id: str, preferences: CarePreferences) -> CarePreferences:
    return await care_preferences_store.save(user_id, preferences)


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
async def push_stream(
    user_id: str | None = Query(default=None, description="Filter events to this user"),
) -> StreamingResponse:
    """SSE stream of proactive push events.

    The frontend long-lives one of these per tab. Events use the same
    text/event-stream wire format as ``/orchestrator/turn/stream``::

        event: reminder_fired
        data: {"id": "...", "text": "...", "fire_at": "..."}

    When ``user_id`` is set, only events whose payload.user_id matches are
    yielded. A 2-second heartbeat keeps the connection unbuffered through
    Cloudflare / nginx.
    """
    bus = get_proactive_push_bus()
    heartbeat_seconds = 2.0

    async def _gen() -> AsyncIterator[bytes]:
        # Send a hello frame immediately so client / proxies open the stream.
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
                    yield b"event: ping\ndata: {}\n\n"
                    continue
                # user_id filter: skip events that don't match
                if user_id is not None and event.payload.get("user_id") != user_id:
                    next_event_task = loop.create_task(subscriber.__anext__())
                    continue
                payload = json.dumps(event.payload, ensure_ascii=False, default=str)
                event_id = f"id: {event.seq}\n" if event.seq is not None else ""
                yield f"{event_id}event: {event.kind}\ndata: {payload}\n\n".encode("utf-8")
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
    user_id: str | None = Query(default=None, description="Filter events to this user"),
) -> Dict[str, Any]:
    """Long-poll friendly snapshot of proactive events after ``since``.

    Use when ``GET /actions/push`` SSE is buffered by Cloudflare / nginx and
    the browser never receives the first bytes in time.

    Passing ``user_id`` scopes the returned events to that user.
    """
    return await get_proactive_push_bus().poll_since(since, user_id=user_id)
