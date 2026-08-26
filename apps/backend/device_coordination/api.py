"""FastAPI routers for the Device Operation Gateway (Lite Mode compatible)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from asyncio import Lock as AsyncLock

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from shared_contracts.models import DeviceInfo, DeviceType, Platform
from shared_runtime.config import get_settings

from .gateway_service import DeviceGatewayService, public_device_dict
from .mqtt_client import DeviceMQTTClient
from .registry import DeviceRegistry
from .task_dispatcher import TaskDispatcher

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/device", tags=["device"])

_registry: Optional[DeviceRegistry] = None
_mqtt: Optional[DeviceMQTTClient] = None
_dispatcher: Optional[TaskDispatcher] = None
_gateway: Optional[DeviceGatewayService] = None


def set_dependencies(
    registry: DeviceRegistry,
    mqtt: Optional[DeviceMQTTClient],
    dispatcher: TaskDispatcher,
    gateway: DeviceGatewayService,
) -> None:
    global _registry, _mqtt, _dispatcher, _gateway
    _registry = registry
    _mqtt = mqtt
    _dispatcher = dispatcher
    _gateway = gateway


def get_registry() -> DeviceRegistry:
    if _registry is None:
        raise RuntimeError("Registry not initialized")
    return _registry


def get_mqtt() -> Optional[DeviceMQTTClient]:
    return _mqtt


def get_dispatcher() -> TaskDispatcher:
    if _dispatcher is None:
        raise RuntimeError("Dispatcher not initialized")
    return _dispatcher


def get_gateway() -> DeviceGatewayService:
    if _gateway is None:
        raise RuntimeError("Device gateway not initialized")
    return _gateway


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    device_id: str
    user_id: str
    device_type: DeviceType
    device_name: str
    platform: Platform
    capabilities: List[str] = Field(default_factory=list)
    ip_address: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    jwt_token: Optional[str] = None


class HeartbeatRequest(BaseModel):
    device_id: str
    device_token: str
    ip_address: Optional[str] = None


class SendCommandRequest(BaseModel):
    user_id: str
    command: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    device_id: Optional[str] = None


class CommandResultRequest(BaseModel):
    command_id: str
    device_id: str
    device_token: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ClaimNextRequest(BaseModel):
    device_id: str
    device_token: str


class ClaimByIdRequest(BaseModel):
    device_id: str
    device_token: str


class MarkRunningRequest(BaseModel):
    device_id: str
    device_token: str


class CancelCommandRequest(BaseModel):
    user_id: str


# ---------------------------------------------------------------------------
# Routes — user vs device facing
# ---------------------------------------------------------------------------


@router.post("/register")
async def register_device(
    req: RegisterRequest,
    gateway: DeviceGatewayService = Depends(get_gateway),
) -> Dict[str, Any]:
    settings = get_settings()
    if req.jwt_token and not settings.lite_mode:
        import jwt

        try:
            jwt_payload = jwt.decode(req.jwt_token, settings.jwt_secret, algorithms=["HS256"])
            if jwt_payload.get("user_id") != req.user_id and jwt_payload.get("scope") != "service":
                raise HTTPException(status_code=403, detail="User mismatch")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            raise HTTPException(status_code=401, detail="Invalid token")

    device = DeviceInfo(
        device_id=req.device_id,
        user_id=req.user_id,
        device_type=req.device_type,
        device_name=req.device_name,
        platform=req.platform,
        capabilities=req.capabilities,
        is_online=True,
        last_heartbeat=datetime.utcnow(),
        ip_address=req.ip_address,
        metadata=req.metadata,
    )
    registered, device_token = await gateway.register_device(device)
    logger.info("api.device_registered", device_id=req.device_id, user_id=req.user_id)
    return {
        "success": True,
        "device_token": device_token,
        "device": public_device_dict(registered),
    }


@router.post("/heartbeat")
async def device_heartbeat(
    req: HeartbeatRequest,
    gateway: DeviceGatewayService = Depends(get_gateway),
) -> Dict[str, Any]:
    try:
        device = await gateway.heartbeat(req.device_id, req.device_token, req.ip_address)
    except PermissionError as exc:
        if str(exc) == "device_not_found":
            raise HTTPException(status_code=404, detail="Device not found") from exc
        raise HTTPException(status_code=401, detail="Invalid device credentials") from exc
    except LookupError:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True, "device": public_device_dict(device)}


@router.get("/list/{user_id}")
async def list_devices(
    user_id: str,
    online_only: bool = False,
    registry: DeviceRegistry = Depends(get_registry),
) -> Dict[str, Any]:
    devices = await registry.list_for_user(user_id, online_only=online_only)
    return {
        "success": True,
        "devices": [public_device_dict(d) for d in devices],
        "count": len(devices),
    }


@router.post("/send_command")
async def send_command(
    req: SendCommandRequest,
    gateway: DeviceGatewayService = Depends(get_gateway),
) -> Dict[str, Any]:
    ok, body, detail = await gateway.send_command(
        user_id=req.user_id,
        command=req.command,
        payload=req.payload,
        device_id=req.device_id,
    )
    if not ok:
        if isinstance(body, dict) and body.get("error") == "high_risk_blocked":
            return {
                "success": False,
                "error": "high_risk_blocked",
                "message": body.get("reason", "该指令已被网关拒绝。"),
            }
        if detail and "Multiple devices online" in detail:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "multi_device", "message": detail},
            )
        if detail and "Delivery failed" in detail:
            raise HTTPException(status_code=502, detail=detail)
        code = status.HTTP_400_BAD_REQUEST
        if detail and "No online devices" in detail:
            code = status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail or "send_command failed")
    return {"success": True, "command": body}


@router.post("/commands/{command_id}/cancel")
async def cancel_command(
    command_id: str,
    req: CancelCommandRequest,
    gateway: DeviceGatewayService = Depends(get_gateway),
) -> Dict[str, Any]:
    try:
        cmd = await gateway.cancel_command(user_id=req.user_id, command_id=command_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Command not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except ValueError as exc:
        if str(exc) == "already_terminal":
            raise HTTPException(status_code=409, detail="Command already finished") from exc
        raise
    return {"success": True, "command": cmd}


@router.post("/command_result")
async def command_result(
    req: CommandResultRequest,
    gateway: DeviceGatewayService = Depends(get_gateway),
) -> Dict[str, Any]:
    try:
        cmd = await gateway.apply_command_result(
            command_id=req.command_id,
            device_id=req.device_id,
            device_token=req.device_token,
            status=req.status,
            result=req.result,
            error=req.error,
        )
    except PermissionError as exc:
        if str(exc) == "device_not_found":
            raise HTTPException(status_code=404, detail="Device not found") from exc
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    except LookupError:
        raise HTTPException(status_code=404, detail="Command not found")
    except ValueError as exc:
        msg = str(exc)
        if msg == "bad_status":
            raise HTTPException(status_code=400, detail="Invalid status") from exc
        raise HTTPException(status_code=409, detail=msg) from exc
    return {"success": True, "command": cmd}


@router.post("/commands/claim_next")
async def claim_next(
    req: ClaimNextRequest,
    gateway: DeviceGatewayService = Depends(get_gateway),
) -> Dict[str, Any]:
    try:
        cmd = await gateway.claim_next(device_id=req.device_id, device_token=req.device_token)
    except PermissionError as exc:
        if str(exc) == "device_not_found":
            raise HTTPException(status_code=404, detail="Device not found") from exc
        raise HTTPException(status_code=401, detail="Invalid device credentials") from exc
    if cmd is None:
        return {"success": True, "command": None}
    return {"success": True, "command": cmd}


@router.post("/commands/{command_id}/claim")
async def claim_command(
    command_id: str,
    req: ClaimByIdRequest,
    gateway: DeviceGatewayService = Depends(get_gateway),
) -> Dict[str, Any]:
    try:
        cmd = await gateway.claim_command(
            command_id=command_id,
            device_id=req.device_id,
            device_token=req.device_token,
        )
    except PermissionError as exc:
        if str(exc) == "device_not_found":
            raise HTTPException(status_code=404, detail="Device not found") from exc
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    except LookupError:
        raise HTTPException(status_code=404, detail="Command not found")
    except ValueError as exc:
        msg = str(exc)
        if msg == "invalid_state":
            raise HTTPException(status_code=409, detail="Command is not claimable") from exc
        if msg == "expired":
            raise HTTPException(status_code=410, detail="Command expired") from exc
        raise
    return {"success": True, "command": cmd}


@router.post("/commands/{command_id}/mark_running")
async def mark_running(
    command_id: str,
    req: MarkRunningRequest,
    gateway: DeviceGatewayService = Depends(get_gateway),
) -> Dict[str, Any]:
    try:
        cmd = await gateway.mark_running(
            command_id=command_id,
            device_id=req.device_id,
            device_token=req.device_token,
        )
    except PermissionError as exc:
        if str(exc) == "device_not_found":
            raise HTTPException(status_code=404, detail="Device not found") from exc
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    except LookupError:
        raise HTTPException(status_code=404, detail="Command not found")
    except ValueError as exc:
        msg = str(exc)
        if msg == "invalid_state":
            raise HTTPException(status_code=409, detail="Command is not runnable") from exc
        if msg == "expired":
            raise HTTPException(status_code=410, detail="Command expired") from exc
        raise
    return {"success": True, "command": cmd}


@router.get("/commands/{command_id}")
async def get_command(
    command_id: str,
    user_id: str = Query(..., description="Owner user id (required for access control)"),
    gateway: DeviceGatewayService = Depends(get_gateway),
) -> Dict[str, Any]:
    try:
        cmd = await gateway.get_command_for_user(command_id=command_id, user_id=user_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Command not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"success": True, "command": cmd}


@router.get("/commands")
async def list_commands(
    user_id: Optional[str] = Query(default=None),
    device_id: Optional[str] = Query(default=None),
    gateway: DeviceGatewayService = Depends(get_gateway),
) -> Dict[str, Any]:
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    cmds = await gateway.list_commands_user(user_id=user_id, device_id=device_id)
    return {"success": True, "commands": cmds, "count": len(cmds)}


@router.get("/audit")
async def list_audit(
    user_id: Optional[str] = Query(default=None),
    device_id: Optional[str] = Query(default=None),
    gateway: DeviceGatewayService = Depends(get_gateway),
) -> Dict[str, Any]:
    if not user_id and not device_id:
        raise HTTPException(status_code=400, detail="user_id or device_id is required")
    rows = await gateway.list_audit(user_id=user_id, device_id=device_id)
    return {"success": True, "audit": rows, "count": len(rows)}


# ── WebSocket push transport ────────────────────────────────────────────

# device_id -> list of active WebSocket connections
_ws_connections: Dict[str, List[WebSocket]] = {}
_ws_lock = AsyncLock()


async def _push_to_device(device_id: str, message: Dict[str, Any]) -> bool:
    """Push a message to all WS connections for a device. Returns True if delivered."""
    async with _ws_lock:
        conns = _ws_connections.get(device_id, [])
    if not conns:
        return False
    dead: List[WebSocket] = []
    for ws in conns:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    if dead:
        async with _ws_lock:
            for ws in dead:
                if ws in _ws_connections.get(device_id, []):
                    _ws_connections[device_id].remove(ws)
    return len(dead) < len(conns)


@router.websocket("/ws/{device_id}")
async def device_websocket(
    websocket: WebSocket,
    device_id: str,
    token: str = Query(...),
    gateway: DeviceGatewayService = Depends(get_gateway),
):
    """Real-time push channel for device commands.
    Devices connect here to receive commands instantly instead of polling.
    Query param: ?token=<device_token>
    """
    # Authenticate
    try:
        await gateway._ensure_device_auth(device_id, token)
    except PermissionError:
        await websocket.close(code=4001, reason="Invalid device credentials")
        return

    await websocket.accept()
    await websocket.send_json({"type": "connected", "device_id": device_id})

    async with _ws_lock:
        _ws_connections.setdefault(device_id, []).append(websocket)
    logger.info("device.ws_connected", device_id=device_id)

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "pong":
                pass  # keep-alive
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        async with _ws_lock:
            conns = _ws_connections.get(device_id, [])
            if websocket in conns:
                conns.remove(websocket)
        logger.info("device.ws_disconnected", device_id=device_id)


# Export the push function so gateway_service can use it
def get_ws_push():
    return _push_to_device


@router.get("/transport/health")
async def transport_health(gateway: DeviceGatewayService = Depends(get_gateway)) -> Dict[str, Any]:
    health = gateway.transport_health()
    health["ws_connections"] = sum(len(v) for v in _ws_connections.values())
    return {"success": True, "transport": health}
