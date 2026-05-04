"""FastAPI routers for gateway_adapter."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from shared.config import get_settings
from shared.models import Platform

from .event_consumer import GatewayEventConsumer
from .session_manager import SessionManager
from .platforms import BasePlatformAdapter, AppWebSocketAdapter

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/gateway", tags=["gateway"])

# ---------------------------------------------------------------------------
# Dependencies (populated in main.py lifespan)
# ---------------------------------------------------------------------------

_consumer: Optional[GatewayEventConsumer] = None
_sessions: Optional[SessionManager] = None
_adapters: Optional[Dict[Platform, BasePlatformAdapter]] = None
_app_ws: Optional[AppWebSocketAdapter] = None


def set_dependencies(
    consumer: Optional[GatewayEventConsumer],
    sessions: SessionManager,
    adapters: Dict[Platform, BasePlatformAdapter],
    app_ws: AppWebSocketAdapter,
) -> None:
    global _consumer, _sessions, _adapters, _app_ws
    _consumer = consumer
    _sessions = sessions
    _adapters = adapters
    _app_ws = app_ws


def get_consumer() -> Optional[GatewayEventConsumer]:
    return _consumer


def get_sessions() -> SessionManager:
    if _sessions is None:
        raise RuntimeError("SessionManager not initialized")
    return _sessions


def get_adapters() -> Dict[Platform, BasePlatformAdapter]:
    if _adapters is None:
        raise RuntimeError("Adapters not initialized")
    return _adapters


def get_app_ws() -> AppWebSocketAdapter:
    if _app_ws is None:
        raise RuntimeError("AppWebSocketAdapter not initialized")
    return _app_ws


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SendRequest(BaseModel):
    user_id: str
    platform: Platform
    content: str
    media: Dict[str, Any] = Field(default_factory=dict)
    reply_to_message_id: Optional[str] = None


class BroadcastRequest(BaseModel):
    user_id: str
    content: str
    exclude_platforms: List[Platform] = Field(default_factory=list)


class ReceiveRequest(BaseModel):
    user_id: str
    platform: Platform
    content: str
    platform_session_id: str
    message_id: Optional[str] = None
    has_voice: bool = False
    voice_data_b64: Optional[str] = None
    has_image: bool = False
    image_urls: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/send")
async def send_message(
    req: SendRequest,
    adapters: Dict[Platform, BasePlatformAdapter] = Depends(get_adapters),
) -> Dict[str, Any]:
    """Send a message to a specific platform."""
    adapter = adapters.get(req.platform)
    if adapter is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Platform not configured")
    msg_id = await adapter.send_message(
        user_id=req.user_id,
        content=req.content,
        media=req.media,
        reply_to_message_id=req.reply_to_message_id,
    )
    logger.info("api.send", user_id=req.user_id, platform=req.platform.value, message_id=msg_id)
    return {"success": True, "message_id": msg_id}


@router.post("/broadcast")
async def broadcast_message(
    req: BroadcastRequest,
    adapters: Dict[Platform, BasePlatformAdapter] = Depends(get_adapters),
) -> Dict[str, Any]:
    """Broadcast a message to all platforms for a user."""
    sent: List[str] = []
    for platform, adapter in adapters.items():
        if platform in req.exclude_platforms:
            continue
        try:
            await adapter.broadcast(req.user_id, req.content)
            sent.append(platform.value)
        except Exception:
            logger.exception("api.broadcast_failed", platform=platform.value, user_id=req.user_id)
    logger.info("api.broadcast", user_id=req.user_id, sent=sent)
    return {"success": True, "sent_to": sent}


@router.post("/receive")
async def receive_message(
    req: ReceiveRequest,
    consumer: Optional[GatewayEventConsumer] = Depends(get_consumer),
    sessions: SessionManager = Depends(get_sessions),
) -> Dict[str, Any]:
    """Webhook receiver for incoming messages from external platforms.

    Converts the incoming message to TurnStartEvent and publishes to Redis.
    """
    if consumer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Event consumer not available in lite mode. Use core_orchestrator /turn directly.",
        )
    session = sessions.get_or_create(req.user_id, req.platform, req.platform_session_id)
    await consumer.publish_turn_start(
        user_id=req.user_id,
        platform=req.platform,
        content=req.content,
        session_id=session.companion_session_id,
        has_voice=req.has_voice,
        voice_data_b64=req.voice_data_b64,
        has_image=req.has_image,
        image_urls=req.image_urls,
    )
    logger.info(
        "api.received",
        user_id=req.user_id,
        platform=req.platform.value,
        session_id=session.companion_session_id,
    )
    return {"success": True, "session_id": session.companion_session_id}


@router.get("/sessions/{user_id}")
async def list_sessions(
    user_id: str,
    sessions: SessionManager = Depends(get_sessions),
) -> Dict[str, Any]:
    """List active sessions for a user."""
    user_sessions = sessions.list_for_user(user_id)
    return {
        "success": True,
        "user_id": user_id,
        "companion_session_id": sessions.get_companion_session(user_id),
        "sessions": [
            {
                "platform": s.platform.value,
                "platform_session_id": s.platform_session_id,
                "companion_session_id": s.companion_session_id,
            }
            for s in user_sessions
        ],
    }


# ---------------------------------------------------------------------------
# WebSocket for standalone App frontend
# ---------------------------------------------------------------------------

@router.websocket("/ws/{user_id}")
async def app_websocket(
    websocket: WebSocket,
    user_id: str,
    app_ws: AppWebSocketAdapter = Depends(get_app_ws),
    consumer: Optional[GatewayEventConsumer] = Depends(get_consumer),
    sessions: SessionManager = Depends(get_sessions),
) -> None:
    """WebSocket endpoint for the standalone App frontend."""
    if consumer is None:
        await websocket.accept()
        await websocket.send_text('{"error": "Lite mode: connect to core_orchestrator /turn directly"}')
        await websocket.close()
        return

    await app_ws.connect(user_id, websocket)
    session = sessions.get_or_create(user_id, Platform.APP, websocket.client.host or "app")

    # Start a background task to read from the WebSocket
    try:
        while True:
            data = await websocket.receive_text()
            payload = __import__("json").loads(data)
            content = payload.get("content", "")
            await consumer.publish_turn_start(
                user_id=user_id,
                platform=Platform.APP,
                content=content,
                session_id=session.companion_session_id,
                has_voice=payload.get("has_voice", False),
                voice_data_b64=payload.get("voice_data_b64"),
                has_image=payload.get("has_image", False),
                image_urls=payload.get("image_urls", []),
            )
            logger.debug("api.ws_message", user_id=user_id, content=content[:50])
    except WebSocketDisconnect:
        await app_ws.disconnect(user_id, websocket)
        logger.info("api.ws_disconnected", user_id=user_id)
    except Exception:
        logger.exception("api.ws_error", user_id=user_id)
        await app_ws.disconnect(user_id, websocket)
