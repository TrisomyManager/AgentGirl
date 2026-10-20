"""Reference-host authorization composition; business ownership stays in its stores."""

import json
from urllib.parse import parse_qs

from sqlalchemy import select
from starlette.routing import Match

from memory_system.db import MemoryORM
from memory_system.session_store import PersistentSessionMemory
from shared_runtime.access import AccessController, AccessError, Principal, device_operation
from shared_runtime.database import AsyncSessionLocal
from voice_layer.media_access import owns_voice_asset

try:
    # FastAPI's lazy included routers require effective, prefixed contexts for
    # introspection. Their outer matches() deliberately discards path_params.
    from fastapi.routing import iter_route_contexts
except ImportError:
    # Earlier supported FastAPI releases flatten routers into app.routes.
    iter_route_contexts = iter

_ADMIN_PREFIXES = (
    "/orchestrator/admin/",
    "/orchestrator/settings/",
    "/orchestrator/debug/",
    "/memory/pipeline/",
    "/memory/maintenance/",
    "/gateway/send",
    "/gateway/broadcast",
    "/gateway/receive",
    "/actions/plugins",
)
_ADMIN_PATHS = {
    "/actions/dispatch",
    "/memory/graph_query",
    "/persona/generate_response",
    "/persona/observe_turn",
    "/persona/update_emotion",
    "/docs",
    "/openapi.json",
    "/redoc",
}
_METADATA = {
    "/access/logout",
    "/actions/list",
    "/actions/capabilities",
    "/actions/mcp/tools",
    "/orchestrator/project_status",
    "/orchestrator/personas",
    "/voice/realtime/status",
    "/voice/transcribe",
    "/voice/synthesize",
    "/voice/stream",
    "/persona/classify_reaction",
}


class HostAccessPolicy:
    def __init__(self, app, controller: AccessController):
        self.app, self.controller = app, controller

    async def __call__(self, scope, body: bytes, principal: Principal):
        if principal.mode == "internal":
            return principal
        params, route_path = {}, ""
        for route in iter_route_contexts(self.app.routes):
            match, child = route.matches(scope)
            if match is Match.FULL:
                params, route_path = child.get("path_params", {}), getattr(route, "path", "")
                break
        query = parse_qs(scope.get("query_string", b"").decode("utf-8", errors="replace"))
        try:
            payload = (
                json.loads(body)
                if body and "application/json" in dict(scope.get("headers", [])).get(b"content-type", b"").decode()
                else {}
            )
        except (ValueError, UnicodeError):
            raise AccessError(400, "请求格式不正确。") from None
        if not isinstance(payload, dict):
            payload = {}
        path = scope["path"]
        # Pending external erasure survives restarts; no fresh data until it finishes.
        if (
            principal.user_id
            and not (path.startswith("/privacy/") and path.endswith(("/erase", "/status")))
            and path != "/access/logout"
        ):
            from core_orchestrator.privacy import no_pending_erasure

            if not await no_pending_erasure(principal.user_id):
                raise AccessError(409, "数据清理尚未完成，请在设置中重试。")
        if principal.mode == "local":
            user = payload.get("user")
            local_user = (
                params.get("user_id")
                or payload.get("user_id")
                or (user.get("user_id") if isinstance(user, dict) else None)
                or query.get("user_id", [None])[0]
            )
            return Principal(local_user or "user_001", "admin", "local")
        if device_operation(scope):
            return await self._device(scope, params, payload, principal)
        if principal.user_id is None:
            raise AccessError(401, "请先登录。")
        ids = [
            value
            for value in (
                params.get("user_id"),
                payload.get("user_id"),
                (payload.get("user") or {}).get("user_id") if isinstance(payload.get("user"), dict) else None,
                (payload.get("params") or {}).get("user_id") if isinstance(payload.get("params"), dict) else None,
            )
            if value is not None
        ]
        ids += query.get("user_id", [])
        if any(value != principal.user_id for value in ids):
            raise AccessError(403, "只能访问当前账号的数据。")
        if path.startswith(_ADMIN_PREFIXES) or path in _ADMIN_PATHS:
            if principal.role != "admin":
                raise AccessError(403, "此操作需要管理员权限。")
            return principal
        if path.startswith("/static/voice/"):
            filename = path.removeprefix("/static/voice/")
            if not await owns_voice_asset(filename, principal.user_id):
                raise AccessError(404, "音频不存在或不属于当前账号。")
            return principal
        owned = bool(ids)
        if "memory_id" in params:
            try:
                from uuid import UUID

                identifier = str(UUID(params["memory_id"]))
            except ValueError:
                raise AccessError(404, "记忆不存在。") from None
            async with AsyncSessionLocal() as session:
                key = UUID(identifier) if session.bind.dialect.name == "postgresql" else identifier
                owner = await session.scalar(select(MemoryORM.user_id).where(MemoryORM.id == key))
            if owner != principal.user_id:
                raise AccessError(404, "记忆不存在。")
            owned = True
        if "reminder_id" in params and route_path.startswith("/actions/reminders/"):
            from action_executor.reminders import ReminderORM

            async with AsyncSessionLocal() as session:
                owner = await session.scalar(select(ReminderORM.user_id).where(ReminderORM.id == params["reminder_id"]))
            if owner != principal.user_id:
                raise AccessError(404, "提醒不存在。")
            owned = True
        device_id = params.get("device_id") or payload.get("device_id") or (query.get("device_id") or [None])[0]
        if device_id:
            from device_coordination.api import get_registry

            device = await get_registry().get(device_id)
            if device and device.user_id != principal.user_id:
                raise AccessError(404, "设备不存在。")
            owned = bool(device) or owned
        session_id = params.get("session_id") or payload.get("session_id") or (query.get("session_id") or [None])[0]
        new_session = path in {"/orchestrator/turn", "/orchestrator/turn/stream", "/voice/realtime"}
        if path == "/voice/realtime" and not session_id:
            from uuid import uuid4

            session_id = uuid4().hex
        if session_id:
            if not isinstance(session_id, str) or not 1 <= len(session_id) <= 128:
                raise AccessError(400, "会话编号格式不正确。")
            try:
                authorized = await PersistentSessionMemory().authorize_session(
                    session_id, principal.user_id, claim=new_session
                )
            except PermissionError:
                raise AccessError(404, "会话不存在或不属于当前账号。") from None
            if not authorized and not new_session:
                raise AccessError(404, "会话不存在。")
            scope["companion.session_id"] = session_id
            owned = True
        if path in _METADATA or owned or (principal.role == "admin" and not route_path):
            return principal
        if principal.role == "admin" and path in {"/orchestrator/status", "/device/transport/health"}:
            return principal
        raise AccessError(403, "当前接口需要账号或资源所有权。")

    async def _device(self, scope, params, payload, principal):
        from device_coordination.api import get_gateway

        protocols = scope.get("subprotocols", [])
        token = payload.get("device_token", "")
        device_id = payload.get("device_id") or params.get("device_id")
        if scope["type"] == "websocket":
            token = protocols[1] if len(protocols) == 2 and protocols[0] == "companion.device" else ""
        try:
            device = await get_gateway().require_device_token(device_id, token)
        except (PermissionError, RuntimeError):
            raise AccessError(403, "设备身份无效。") from None
        if principal.user_id and principal.user_id != device.user_id:
            raise AccessError(403, "只能访问当前账号的设备。")
        scope["companion.device_token"] = token
        return Principal(device.user_id, "device", "device")
