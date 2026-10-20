"""Real-time voice pipeline over WebSocket.

Delegates to a configured ``RealtimeVoiceProvider``. The provider is
selected via ``COMPANION_REALTIME_VOICE_PROVIDER`` (default ``"volc_realtime"``).

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

import asyncio
import contextlib
import json

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from shared_contracts.audio_transport import (
    MAX_AUDIO_BYTES,
    PROTOCOL,
    AudioFrameError,
    decode_audio_frame,
    encode_audio_frame,
)
from shared_runtime.access import current_principal
from voice_layer.providers.realtime import get_provider, init_registry, is_registry_initialized

logger = structlog.get_logger("voice_layer.realtime")


async def realtime_handler(websocket: WebSocket) -> None:
    """Entry point used by the FastAPI route /voice/realtime."""
    await websocket.accept()
    wire = websocket.query_params.get("audio_protocol", "raw")
    if wire not in {"raw", PROTOCOL}:
        await websocket.close(code=1002, reason="不支持的语音传输版本。")
        return
    if "audio_protocol" in websocket.query_params:
        await websocket.send_json(
            {"type": "transport_ready", "audio_protocol": wire, "max_audio_bytes": MAX_AUDIO_BYTES}
        )
    send_lock = asyncio.Lock()
    stream_id, next_stream, send_sequence, receive_sequence = 0, 0, 0, 0
    principal = current_principal.get()
    fixed_user = principal.user_id if principal else None
    fixed_session = websocket.scope.get("companion.session_id") or websocket.query_params.get("session_id")
    logger.info("realtime.connected")

    voice_profile_id: str | None = websocket.query_params.get("voice_profile_id")

    if not is_registry_initialized():
        init_registry()

    provider = get_provider()
    if provider.provider_name == "cloud":
        from voice_layer.providers.realtime.cloud_realtime import CloudRealtimeProvider

        factory = getattr(websocket.app.state, "voice_asr_factory", None)
        if factory is not None and type(provider) is CloudRealtimeProvider:
            provider = CloudRealtimeProvider(asr_factory=factory)
    if provider.provider_name == "volc_realtime":
        from voice_layer.providers.realtime.volc_realtime import VolcRealtimeProvider

        # Each socket owns a vendor session ID and its own voice selection.
        provider = VolcRealtimeProvider(voice_profile_id=voice_profile_id)
    logger.info(
        "realtime.provider_selected",
        provider=provider.provider_name,
        voice_profile_id=voice_profile_id,
    )

    async def _deliver(sender):
        # Settle a send before propagating cancellation, so a packet accepted by
        # the transport cannot be reissued under the same sequence number.
        async def bounded_send():
            async with asyncio.timeout(5):
                await sender

        task = asyncio.create_task(bounded_send())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        return cancelled

    async def _send_json(data: dict) -> None:
        nonlocal stream_id, next_stream
        async with send_lock:
            if wire == PROTOCOL and data.get("type") in {"assistant_sentence_start", "tts_start"}:
                next_stream += 1
                if next_stream > 0xFFFFFFFF:
                    raise AudioFrameError("Audio stream counter exhausted")
                stream_id = next_stream
                data = {**data, "audio_stream_id": stream_id, "audio_protocol": PROTOCOL}
            elif data.get("type") == "interrupted":
                stream_id = 0
            encoded = json.dumps(data, ensure_ascii=False)
            if len(encoded.encode()) > 65536:
                raise AudioFrameError("Control event too large")
            if await _deliver(websocket.send_text(encoded)):
                raise asyncio.CancelledError

    async def _send_bytes(data: bytes) -> None:
        nonlocal send_sequence
        if not data:
            return
        if len(data) > MAX_AUDIO_BYTES:
            raise AudioFrameError("Audio payload too large")
        async with send_lock:
            if wire == PROTOCOL:
                if not stream_id:
                    return  # Unannounced/interrupted audio never becomes a new stream.
                data = encode_audio_frame(data, stream_id=stream_id, sequence=send_sequence)
            cancelled = await _deliver(websocket.send_bytes(data))
            if wire == PROTOCOL:
                send_sequence += 1
            if cancelled:
                raise asyncio.CancelledError

    async def _receive() -> dict:
        nonlocal receive_sequence
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
            data = msg["bytes"]
            if wire == PROTOCOL:
                try:
                    frame = decode_audio_frame(data)
                    if frame.stream_id != 0 or frame.sequence != receive_sequence:
                        raise AudioFrameError("Unexpected uplink stream or sequence")
                except AudioFrameError:
                    await websocket.close(code=1002, reason="语音帧格式或顺序不正确。")
                    return {"type": "disconnect"}
                data = frame.payload
                receive_sequence += 1
            elif not data or len(data) > MAX_AUDIO_BYTES:
                await websocket.close(code=1009, reason="语音帧大小不正确。")
                return {"type": "disconnect"}
            return {"type": "binary", "data": data}
        if "text" in msg and msg["text"] is not None:
            if len(msg["text"].encode()) > 65536:
                await websocket.close(code=1009, reason="控制消息过大。")
                return {"type": "disconnect"}
            try:
                control = json.loads(msg["text"])
                if not isinstance(control, dict) or not isinstance(control.get("type"), str):
                    raise ValueError("Invalid control message")
            except ValueError:
                await websocket.close(code=1002, reason="控制消息格式不正确。")
                return {"type": "disconnect"}
            if (
                fixed_user
                and control.get("type") == "start"
                and (
                    control.get("user_id", fixed_user) != fixed_user
                    or control.get("session_id", fixed_session) != fixed_session
                )
            ):
                await _send_json(
                    {"type": "error", "msg": "通话中不能切换账号或会话，请重新连接。", "recoverable": True}
                )
                return {"type": "text", "data": '{"type":"ping"}'}
            return {"type": "text", "data": msg["text"]}
        return {"type": "disconnect"}

    q_user = (websocket.query_params.get("user_id") or "").strip()
    memory_user_id = fixed_user or q_user or "anonymous"
    q_sess = (websocket.query_params.get("session_id") or "").strip()
    memory_session_id = fixed_session or q_sess or None

    try:
        await provider.run(
            ws_send_json=_send_json,
            ws_send_bytes=_send_bytes,
            ws_receive=_receive,
            memory_user_id=memory_user_id,
            memory_session_id=memory_session_id,
        )
    except Exception as exc:
        logger.warning("realtime.provider_error", reason=type(exc).__name__)
        with contextlib.suppress(Exception):
            await _send_json({"type": "error", "msg": "实时语音连接中断，请重新连接。"})
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
        logger.info("realtime.disconnected")
