"""Host access keys, revocable sessions and an ASGI boundary; no business imports."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import secrets
import time
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from shared_runtime.user_lifecycle import StaleUserOperation, user_operation, user_unavailable


@dataclass(frozen=True)
class Principal:
    user_id: str | None
    role: str
    mode: str = "key"
    credential: str = field(default="", repr=False)
    session: str = field(default="", repr=False)


current_principal: ContextVar[Principal | None] = ContextVar("companion_principal", default=None)
_INTERNAL = object()
_reference_app = None


def trusted_internal_app(app):
    """The capability is an in-process object, never a spoofable network header."""

    async def call(scope, receive, send):
        scope = {**scope, "companion.internal": _INTERNAL, "companion.principal": current_principal.get()}
        await app(scope, receive, send)

    return call


def is_internal(scope):
    return scope.get("companion.internal") is _INTERNAL


def attach_reference_app(app):
    global _reference_app
    _reference_app = trusted_internal_app(app)


def reference_http_kwargs():
    from shared_runtime.config import get_settings

    if _reference_app is None or get_settings().self_base_url:
        return {}
    import httpx

    return {"transport": httpx.ASGITransport(app=_reference_app)}


class AccessKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    user_id: str = Field(pattern=r"^[a-zA-Z0-9_:.@-]{1,128}$")
    role: Literal["user", "admin"] = "user"
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)


class AccessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_keys: list[AccessKey] = Field(min_length=1, max_length=128)


class AccessError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


class AccessController:
    def __init__(self, config_file: Path | None = None, *, origins=(), session_seconds=8 * 3600):
        self.config_file = config_file
        self.origins = set(origins)
        self.session_seconds = session_seconds
        self._keys: dict[str, AccessKey] = {}
        self._revision = None
        self._valid = False
        self._sessions: dict[str, tuple[str, float]] = {}
        self._active: dict[str, set] = {}

    @property
    def mode(self):
        return "key" if self.config_file else "local"

    def _reload(self):
        if self.config_file is None:
            return
        try:
            if self.config_file.stat().st_size > 65536:
                raise ValueError("Access file too large")
            raw = self.config_file.read_bytes()
            revision = hashlib.sha256(raw).digest()
            if revision == self._revision and self._valid:
                return
            config = AccessConfig.model_validate_json(raw)
            keys = {entry.sha256: entry for entry in config.access_keys}
            if len(keys) != len(config.access_keys):
                raise ValueError("Duplicate access credentials")
            changed = {digest for digest, value in self._keys.items() if keys.get(digest) != value}
            self._sessions = {digest: value for digest, value in self._sessions.items() if value[0] not in changed}
            self._keys, self._revision, self._valid = keys, revision, True
        except Exception:
            self._keys, self._revision, self._valid = {}, None, False
        self._sessions = {
            key: value
            for key, value in self._sessions.items()
            if value[0] in self._keys and value[1] > time.monotonic()
        }

    def _credential(self, token: str):
        if not token or len(token) > 512:
            return None
        self._reload()
        digest = hashlib.sha256(token.encode()).hexdigest()
        session_digest = digest
        session = self._sessions.get(digest)
        if session:
            digest = session[0] if session[1] > time.monotonic() else ""
        key = self._keys.get(digest)
        return (
            Principal(key.user_id, key.role, credential=digest, session=session_digest if session else "")
            if key
            else None
        )

    def valid(self, principal: Principal):
        self._reload()
        key = self._keys.get(principal.credential)
        return bool(
            key
            and key.user_id == principal.user_id
            and key.role == principal.role
            and (not principal.session or principal.session in self._sessions)
        )

    def local_allowed(self, scope):
        headers = Headers(scope=scope)
        try:
            local_peer = ipaddress.ip_address((scope.get("client") or ("",))[0]).is_loopback
        except ValueError:
            local_peer = False
        if not local_peer or any(name in headers for name in ("forwarded", "x-forwarded-for", "x-forwarded-host")):
            return False
        origin = headers.get("origin")
        if origin and origin not in self.origins:
            return False
        # Browser requests also need a loopback Host, including DNS-rebinding requests.
        if origin or "sec-fetch-site" in headers:
            host = urlsplit("http://" + headers.get("host", "")).hostname
            if host not in {"localhost", "127.0.0.1", "::1"}:
                return False
        return True

    def resolve(self, scope):
        if is_internal(scope):
            return scope.get("companion.principal") or Principal(None, "admin", "internal")
        if self.mode == "local":
            if self.local_allowed(scope):
                return Principal(None, "admin", "local")
            raise AccessError(403, "未配置访问密钥时，仅允许本机访问。")
        headers = Headers(scope=scope)
        authorization = headers.get("authorization", "")
        token = authorization[7:] if authorization.startswith("Bearer ") else ""
        if scope["type"] == "websocket" and not token:
            protocols = scope.get("subprotocols", [])
            if len(protocols) == 2 and protocols[0] == "companion.session":
                token = protocols[1]
        principal = self._credential(token)
        if principal is None:
            raise AccessError(401, "请使用本机配置的访问密钥登录。")
        return principal

    def login(self, key: str):
        self._reload()
        digest = hashlib.sha256(key.encode()).hexdigest() if isinstance(key, str) and 20 <= len(key) <= 512 else ""
        entry = self._keys.get(digest)
        if not entry:
            raise AccessError(401, "访问密钥无效，或服务端访问配置不可用。")
        if len(self._sessions) >= 1024:
            raise AccessError(429, "登录会话已满，请稍后重试。")
        token = secrets.token_urlsafe(32)
        self._sessions[hashlib.sha256(token.encode()).hexdigest()] = (digest, time.monotonic() + self.session_seconds)
        return token, Principal(entry.user_id, entry.role)

    def logout(self, scope):
        header = Headers(scope=scope).get("authorization", "")
        if header.startswith("Bearer "):
            digest = hashlib.sha256(header[7:].encode()).hexdigest()
            self._sessions.pop(digest, None)
            for task, event in tuple(self._active.get(digest, ())):
                if task is not asyncio.current_task():
                    event.set()
                    task.cancel()


DEVICE_OPERATIONS = {"/device/heartbeat", "/device/command_result", "/device/commands/claim_next"}


def device_operation(scope):
    path = scope["path"]
    return (
        scope["type"] == "http"
        and scope.get("method") == "POST"
        and (
            path in DEVICE_OPERATIONS
            or (path.startswith("/device/commands/") and path.rsplit("/", 1)[-1] in {"claim", "mark_running"})
        )
    ) or (scope["type"] == "websocket" and path.startswith("/device/ws/"))


class AccessMiddleware:
    def __init__(self, app, *, controller: AccessController, authorize, max_body_bytes=16 * 1024 * 1024):
        self.app, self.controller, self.authorize = app, controller, authorize
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        # Key identities are known before body buffering or session claims. Keep
        # that whole authorization window inside the erasure barrier as well.
        principal = None
        if scope["type"] in {"http", "websocket"}:
            with suppress(AccessError):
                principal = self.controller.resolve(scope)
        skip = scope.get("path") in {"/", "/health", "/access/status", "/access/login", "/access/logout"} or (
            scope.get("path", "").startswith("/privacy/") and scope["path"].endswith(("/erase", "/status"))
        )
        if principal and principal.mode == "key" and not skip and not is_internal(scope):
            try:
                async with user_operation(principal.user_id, postcheck=False):
                    return await self._call(scope, receive, send)
            except StaleUserOperation:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 4401, "reason": "用户数据正在清理。"})
                else:
                    await JSONResponse({"detail": "用户数据正在清理，请稍后重试。"}, 409)(scope, receive, send)
                return
        await self._call(scope, receive, send)

    async def _call(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        public = scope["path"] in {"/", "/health", "/access/status", "/access/login"}
        if scope.get("method") == "OPTIONS":
            return await self.app(scope, receive, send)
        try:
            try:
                principal = self.controller.resolve(scope)
            except AccessError:
                if not public and not device_operation(scope):
                    raise
                principal = Principal(
                    None, "device_pending" if device_operation(scope) else "anonymous", self.controller.mode
                )
            body = b""
            if scope["type"] == "http":
                chunks, size = [], 0
                async with asyncio.timeout(30):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        data = message.get("body", b"")
                        size += len(data)
                        if size > self.max_body_bytes:
                            raise AccessError(413, "请求内容过大，请缩小图片或音频后重试。")
                        chunks.append(data)
                        if not message.get("more_body"):
                            break
                body = b"".join(chunks)
            if not public and not is_internal(scope):
                principal = await self.authorize(scope, body, principal)
            scope["companion.principal"] = principal
            token = current_principal.set(principal)
            first = True
            started = completed = False
            revoked = asyncio.Event()
            owner = asyncio.current_task()
            identity = principal.session or principal.credential
            monitor = None

            async def checked_send(message):
                nonlocal started, completed
                if message["type"] in {"http.response.start", "websocket.accept"}:
                    started = True
                if message["type"] == "websocket.accept" and not message.get("subprotocol"):
                    protocols = scope.get("subprotocols", [])
                    if len(protocols) == 2 and protocols[0] in {"companion.session", "companion.device"}:
                        # Browsers require a selected protocol when they offered
                        # one. Acknowledge only the public name, never the token.
                        message = {**message, "subprotocol": protocols[0]}
                if message["type"] == "http.response.start" and not public:
                    headers = [
                        (key, value) for key, value in message.get("headers", []) if key.lower() != b"cache-control"
                    ]
                    message = {**message, "headers": headers + [(b"cache-control", b"no-store")]}
                if message["type"] == "http.response.body" and not message.get("more_body"):
                    completed = True
                if message["type"] == "websocket.close":
                    completed = True
                await send(message)

            async def watch_access():
                while True:
                    await asyncio.sleep(0.5)
                    valid = self.controller.valid(principal) if principal.mode == "key" else True
                    if principal.mode == "device" and scope["type"] == "websocket":
                        try:
                            await self.authorize(scope, body, principal)
                        except AccessError:
                            valid = False
                    if not valid:
                        revoked.set()
                        owner.cancel()
                        return

            if not is_internal(scope) and principal.mode in {"key", "device"} and principal.role != "anonymous":
                self.controller._active.setdefault(identity, set()).add((owner, revoked))
                monitor = asyncio.create_task(watch_access(), name="access-session-monitor")

            async def replay():
                nonlocal first
                if first and scope["type"] == "http":
                    first = False
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            try:
                # Privacy endpoints own the exclusive erasure barrier themselves.
                async with user_operation(
                    None
                    if scope["path"] == "/access/logout"
                    or (scope["path"].startswith("/privacy/") and scope["path"].endswith(("/erase", "/status")))
                    else principal.user_id
                ):
                    await self.app(scope, replay, checked_send)
            except asyncio.CancelledError as error:
                cleared = isinstance(error, StaleUserOperation) or user_unavailable(principal.user_id)
                if not revoked.is_set() and not cleared:
                    raise
                owner.uncancel()
                if not completed:
                    if scope["type"] == "websocket":
                        await send(
                            {"type": "websocket.close", "code": 4401, "reason": "登录已失效或用户数据正在清理。"}
                        )
                    elif started:
                        await send({"type": "http.response.body", "body": b"", "more_body": False})
                    else:
                        await JSONResponse(
                            {"detail": "用户数据正在清理，请稍后重试。"}
                            if cleared
                            else {"detail": "登录已失效，请重新登录。"},
                            409 if cleared else 401,
                        )(scope, receive, send)
            finally:
                if monitor:
                    monitor.cancel()
                    await asyncio.gather(monitor, return_exceptions=True)
                    active = self.controller._active.get(identity)
                    if active is not None:
                        active.discard((owner, revoked))
                        if not active:
                            self.controller._active.pop(identity, None)
                current_principal.reset(token)
        except (AccessError, TimeoutError) as error:
            status = error.status if isinstance(error, AccessError) else 408
            detail = error.message if isinstance(error, AccessError) else "请求超时，请重试。"
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4401 if status == 401 else 4403, "reason": detail})
            else:
                await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)


def access_router(controller: AccessController):
    router = APIRouter(prefix="/access", tags=["access"])

    @router.get("/status")
    async def status(request: Request):
        principal = request.scope.get("companion.principal")
        authenticated = bool(principal and principal.role not in {"anonymous", "device_pending"})
        return JSONResponse(
            {
                "mode": controller.mode,
                "authenticated": authenticated,
                "user_id": principal.user_id if authenticated else None,
                "role": principal.role if authenticated else None,
            },
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/login")
    async def login(request: Request):
        try:
            data = await request.json()
            session_token, principal = controller.login(data.get("access_key", ""))
            return JSONResponse(
                {
                    "mode": "key",
                    "authenticated": True,
                    "user_id": principal.user_id,
                    "role": principal.role,
                    "session_token": session_token,
                },
                headers={"Cache-Control": "no-store"},
            )
        except AccessError as error:
            return JSONResponse({"detail": error.message}, error.status, headers={"Cache-Control": "no-store"})
        except (ValueError, TypeError, AttributeError):
            return JSONResponse(
                {"detail": "访问密钥无效，或服务端访问配置不可用。"}, 401, headers={"Cache-Control": "no-store"}
            )

    @router.post("/logout")
    async def logout(request: Request):
        controller.logout(request.scope)
        return {"logged_out": True}

    return router
