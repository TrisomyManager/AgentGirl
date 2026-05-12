"""Real-time voice pipeline over WebSocket.

Delegates to a configured ``RealtimeVoiceProvider``. The provider is
selected via ``COMPANION_REALTIME_VOICE_PROVIDER`` (default ``"local"``).

Unified event protocol (server → client):
    {"type": "ready"}
    {"type": "user_transcript_delta", "text": "..."}
    {"type": "user_transcript_final", "text": "..."}
    {"type": "assistant_text_delta", "text": "..."}
    {"type": "assistant_sentence_start", "text": "..."}
    {"type": "assistant_audio_chunk"}  (optional, sent as binary)
    {"type": "assistant_audio_done"}
    {"type": "interrupted"}
    {"type": "error", "msg": "..."}
    {"type": "pong"}
"""

from __future__ import annotations

import contextlib
import json

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from voice_layer.providers.realtime import get_provider, init_registry, is_registry_initialized

logger = structlog.get_logger("voice_layer.realtime")


async def realtime_handler(websocket: WebSocket) -> None:
    """Entry point used by the FastAPI route /voice/realtime."""
    await websocket.accept()
    logger.info("realtime.connected")

    voice_profile_id: str | None = websocket.query_params.get("voice_profile_id")

    if not is_registry_initialized():
        init_registry()

    provider = get_provider()
    logger.info(
        "realtime.provider_selected",
        provider=provider.provider_name,
        voice_profile_id=voice_profile_id,
    )

    async def _send_json(data: dict) -> None:
        with contextlib.suppress(Exception):
            await websocket.send_text(json.dumps(data, ensure_ascii=False))

    async def _send_bytes(data: bytes) -> None:
        with contextlib.suppress(Exception):
            await websocket.send_bytes(data)

    async def _receive() -> dict:
        try:
            msg = await websocket.receive()
        except WebSocketDisconnect:
            return {"type": "disconnect"}
        except Exception as exc:
            logger.warning("realtime.receive_failed", error=str(exc))
            return {"type": "disconnect"}

        if msg.get("type") == "websocket.disconnect":
            return {"type": "disconnect"}
        if "bytes" in msg and msg["bytes"] is not None:
            return {"type": "binary", "data": msg["bytes"]}
        if "text" in msg and msg["text"] is not None:
            return {"type": "text", "data": msg["text"]}
        return {"type": "disconnect"}

    q_user = (websocket.query_params.get("user_id") or "").strip()
    memory_user_id = q_user or "anonymous"
    q_sess = (websocket.query_params.get("session_id") or "").strip()
    memory_session_id = q_sess or None

    try:
        await provider.run(
            ws_send_json=_send_json,
            ws_send_bytes=_send_bytes,
            ws_receive=_receive,
            memory_user_id=memory_user_id,
            memory_session_id=memory_session_id,
        )
    except Exception as exc:
        logger.exception("realtime.provider_error", error=str(exc))
    finally:
        logger.info("realtime.disconnected")
