"""FastAPI routers for device coordination."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from shared_runtime.config import get_settings
from shared_contracts.models import DeviceInfo, DeviceType, Platform

from .mqtt_client import DeviceMQTTClient
from .registry import DeviceRegistry
from .task_dispatcher import TaskDispatcher

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/device", tags=["device"])

# ---------------------------------------------------------------------------
# Dependencies (populated in main.py lifespan)
# ---------------------------------------------------------------------------

_registry: Optional[DeviceRegistry] = None
_mqtt: Optional[DeviceMQTTClient] = None
_dispatcher: Optional[TaskDispatcher] = None


def set_dependencies(registry: DeviceRegistry, mqtt: DeviceMQTTClient, dispatcher: TaskDispatcher) -> None:
    global _registry, _mqtt, _dispatcher
    _registry = registry
    _mqtt = mqtt
    _dispatcher = dispatcher


def get_registry() -> DeviceRegistry:
    if _registry is None:
        raise RuntimeError("Registry not initialized")
    return _registry


def get_mqtt() -> DeviceMQTTClient:
    if _mqtt is None:
        raise RuntimeError("MQTT client not initialized")
    return _mqtt


def get_dispatcher() -> TaskDispatcher:
    if _dispatcher is None:
        raise RuntimeError("Dispatcher not initialized")
    return _dispatcher


# ---------------------------------------------------------------------------
# JWT validation helper
# ---------------------------------------------------------------------------

import jwt


def _validate_jwt(token: str) -> Dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


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
    jwt_token: str


class HeartbeatRequest(BaseModel):
    device_id: str
    ip_address: Optional[str] = None


class SendCommandRequest(BaseModel):
    device_id: str
    command: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class BroadcastRequest(BaseModel):
    user_id: str
    command: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    task_type: str = "notification"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register")
async def register_device(
    req: RegisterRequest,
    registry: DeviceRegistry = Depends(get_registry),
    mqtt: DeviceMQTTClient = Depends(get_mqtt),
) -> Dict[str, Any]:
    """Register a new device (JWT required)."""
    jwt_payload = _validate_jwt(req.jwt_token)
    # Ensure token user_id matches request (or allow service tokens)
    if jwt_payload.get("user_id") != req.user_id and jwt_payload.get("scope") != "service":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User mismatch")

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
    registered = await registry.register(device)
    await mqtt.subscribe_device(req.device_id)
    logger.info("api.device_registered", device_id=req.device_id, user_id=req.user_id)
    return {"success": True, "device": registered.model_dump()}


@router.post("/heartbeat")
async def device_heartbeat(
    req: HeartbeatRequest,
    registry: DeviceRegistry = Depends(get_registry),
) -> Dict[str, Any]:
    """Receive a heartbeat (also accepted via MQTT)."""
    device = await registry.heartbeat(req.device_id, req.ip_address)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return {"success": True, "device": device.model_dump()}


@router.get("/list/{user_id}")
async def list_devices(
    user_id: str,
    online_only: bool = False,
    registry: DeviceRegistry = Depends(get_registry),
) -> Dict[str, Any]:
    """List all devices for a user."""
    devices = await registry.list_for_user(user_id, online_only=online_only)
    return {"success": True, "devices": [d.model_dump() for d in devices], "count": len(devices)}


@router.post("/send_command")
async def send_command(
    req: SendCommandRequest,
    mqtt: DeviceMQTTClient = Depends(get_mqtt),
    registry: DeviceRegistry = Depends(get_registry),
) -> Dict[str, Any]:
    """Send a command to a specific device via MQTT."""
    device = await registry.get(req.device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    if not device.is_online:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device is offline")
    await mqtt.send_command(req.device_id, req.command, req.payload)
    logger.info("api.command_sent", device_id=req.device_id, command=req.command)
    return {"success": True, "device_id": req.device_id, "command": req.command}


@router.post("/broadcast")
async def broadcast_command(
    req: BroadcastRequest,
    mqtt: DeviceMQTTClient = Depends(get_mqtt),
    dispatcher: TaskDispatcher = Depends(get_dispatcher),
) -> Dict[str, Any]:
    """Broadcast a command to all suitable devices for a user."""
    devices = await dispatcher.broadcast(req.user_id, req.task_type, req.payload)
    sent: List[str] = []
    for device in devices:
        await mqtt.send_command(device.device_id, req.command, req.payload)
        sent.append(device.device_id)
    logger.info("api.broadcast_sent", user_id=req.user_id, command=req.command, count=len(sent))
    return {"success": True, "sent_to": sent, "count": len(sent)}
