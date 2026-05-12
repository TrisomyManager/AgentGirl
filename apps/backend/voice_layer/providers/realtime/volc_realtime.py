"""Volcengine end-to-end realtime voice provider.

Connects to Volcengine (火山引擎) realtime dialogue API via WebSocket,
handles the binary protocol, and normalizes vendor events into the
project's unified realtime event model.

References:
    https://www.volcengine.com/docs/6561/1594356?lang=zh

Interrupt semantics:
    On user interrupt a ``EVENT_FINISH_SESSION`` frame is sent to cancel
    the current turn, local partial ASR text is cleared, and an
    ``interrupted`` event is emitted to the frontend.

Audio format:
    The provider requests PCM 16-bit mono via the session config.
    The ``audio_config`` block dual-writes ``channel`` and ``channels``
    because different Volc API versions use different field names.
    ``channel`` (singular) is the documented field per the official spec.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import gzip
import json
import os
import struct
import uuid
from typing import Any

import structlog
import websockets
from websockets.exceptions import ConnectionClosed

from shared_runtime.config import get_settings
from voice_layer.resolver import resolve_voice

logger = structlog.get_logger("voice_layer.providers.volc_realtime")

# ---------------------------------------------------------------------------
# Binary protocol constants
# ---------------------------------------------------------------------------

PROTOCOL_VERSION = 0b0001
DEFAULT_HEADER_SIZE = 0b0001

FULL_CLIENT_REQUEST = 0b0001
AUDIO_ONLY_REQUEST = 0b0010
FULL_SERVER_RESPONSE = 0b1001
AUDIO_SERVER_RESPONSE = 0b1011

NO_SEQUENCE = 0b0000
NEG_SEQUENCE = 0b0010
HAS_EVENT_ID = 0b0100

JSON_SERIALIZATION = 0b0001
NO_SERIALIZATION = 0b0000
GZIP_COMPRESSION = 0b0001
NO_COMPRESSION = 0b0000

# Client events
EVENT_START_CONNECTION = 1
EVENT_FINISH_CONNECTION = 2
EVENT_START_SESSION = 100
EVENT_FINISH_SESSION = 102
EVENT_TASK_REQUEST = 200

# Server events
EVENT_CONNECTION_STARTED = 50
EVENT_CONNECTION_FAILED = 51
EVENT_SESSION_STARTED = 150
EVENT_SESSION_FINISHED = 152
EVENT_SESSION_FAILED = 153
EVENT_TTS_SENTENCE_START = 350
EVENT_TTS_RESPONSE = 352
EVENT_TTS_ENDED = 359
EVENT_ASR_RESPONSE = 451
EVENT_ASR_ENDED = 459
EVENT_CHAT_RESPONSE = 550
EVENT_CHAT_ENDED = 559

_DEFAULT_SYSTEM_PROMPT = (
    "你是一个温柔体贴、富有共情力的 AI 陪伴助手。"
    "用户正在通过语音和你对话，请用自然、口语化的中文短句回复，"
    "每次回复控制在 1-3 句话以内，避免书面语和列表格式。"
)

# Requested audio output format: 16-bit PCM mono
_AUDIO_FORMAT = "pcm"
_AUDIO_SAMPLE_RATE = 24000
_AUDIO_CHANNELS = 1
_AUDIO_BIT_DEPTH = 16

# Feature flag: strip leading sentence_id from NO_SERIALIZATION TTS payloads.
# Set VOLC_TTS_STRIP_SENTENCE_ID=1 to enable.  Default off (0).
_STRIP_SENTENCE_ID = os.getenv("VOLC_TTS_STRIP_SENTENCE_ID", "1") == "1"


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy with sensitive header values redacted for logging."""
    sensitive = {"x-api-access-key", "x-api-app-key"}
    return {
        k: (v[:4] + "****" if k.lower() in sensitive and len(v) > 4 else "****")
        if k.lower() in sensitive
        else v
        for k, v in headers.items()
    }


# ---------------------------------------------------------------------------
# Protocol builders and parsers
# ---------------------------------------------------------------------------

def _make_header(
    message_type: int = FULL_CLIENT_REQUEST,
    flags: int = NO_SEQUENCE,
    serialization: int = JSON_SERIALIZATION,
    compression: int = GZIP_COMPRESSION,
) -> bytes:
    return bytes([
        (PROTOCOL_VERSION << 4) | DEFAULT_HEADER_SIZE,
        (message_type << 4) | flags,
        (serialization << 4) | compression,
        0x00,
    ])


def _build_event_payload(event_id: int, data: dict[str, Any] | None = None) -> bytes:
    header = _make_header(flags=(NO_SEQUENCE | HAS_EVENT_ID))
    if data is None:
        data = {}
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    body = gzip.compress(body)
    payload = struct.pack(">I", event_id) + body
    size = struct.pack(">I", len(payload))
    return header + size + payload


def _build_audio_payload(audio_bytes: bytes, is_last: bool = False) -> bytes:
    flags = NEG_SEQUENCE if is_last else (NO_SEQUENCE | HAS_EVENT_ID)
    header = _make_header(
        message_type=AUDIO_ONLY_REQUEST,
        flags=flags,
        serialization=NO_SERIALIZATION,
        compression=NO_COMPRESSION,
    )
    event_id_bytes = struct.pack(">I", EVENT_TASK_REQUEST)
    payload = event_id_bytes + audio_bytes
    size = struct.pack(">I", len(payload))
    return header + size + payload


def _build_finish_session() -> bytes:
    return _build_event_payload(EVENT_FINISH_SESSION, {})


def _parse_response(message: bytes) -> dict[str, Any]:
    """Parse a single binary response frame from the Volcengine server.

    Returns a dict that always contains the raw payload under ``_raw_payload``
    for non-JSON frames (e.g. raw audio).  JSON frames are decompressed and
    parsed into top-level keys.
    """
    if len(message) < 8:
        return {"_parse_error": "message too short", "_raw_len": len(message)}

    msg_type = (message[1] >> 4) & 0x0F
    flags = message[1] & 0x0F
    serialization = (message[2] >> 4) & 0x0F
    compression = (message[2] >> 0) & 0x0F

    header_size = (message[0] & 0x0F) * 4
    if header_size < 4:
        header_size = 4

    offset = header_size
    if offset + 4 > len(message):
        return {"_parse_error": "no payload size", "_raw_len": len(message)}

    payload_size = struct.unpack(">I", message[offset:offset + 4])[0]
    offset += 4

    if offset + payload_size > len(message):
        return {"_parse_error": "payload truncated", "_raw_len": len(message)}

    payload = message[offset:offset + payload_size]

    event_id: int | None = None
    if flags & HAS_EVENT_ID and len(payload) >= 4:
        event_id = struct.unpack(">I", payload[:4])[0]
        payload = payload[4:]

    result: dict[str, Any] = {
        "_msg_type": msg_type,
        "_flags": flags,
        "_serialization": serialization,
        "_compression": compression,
        "_event_id": event_id,
    }

    if serialization == JSON_SERIALIZATION:
        body = payload
        if compression == GZIP_COMPRESSION:
            with contextlib.suppress(Exception):
                body = gzip.decompress(body)
        try:
            parsed = json.loads(body.decode("utf-8"))
            if isinstance(parsed, dict):
                result.update(parsed)
            else:
                result["_json_value"] = parsed
        except Exception:
            result["_raw_payload"] = body[:500]
    else:
        result["_raw_payload"] = payload

    return result


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class VolcRealtimeProvider:
    """Volcengine end-to-end realtime dialogue provider.

    Credentials come from ``COMPANION_VOLC_APP_ID`` / ``COMPANION_VOLC_ACCESS_TOKEN``
    environment variables.  They are never hard-coded, logged, or exposed to the
    frontend.
    """

    def __init__(
        self,
        app_id: str | None = None,
        access_token: str | None = None,
        resource_id: str | None = None,
        endpoint: str | None = None,
        system_prompt: str | None = None,
        persona_context: str | None = None,
        memory_context: str | None = None,
        voice_profile_id: str | None = None,
    ) -> None:
        settings = get_settings()
        self._app_id = app_id or settings.volc_app_id or ""
        self._access_token = access_token or settings.volc_access_token or ""
        self._resource_id = resource_id or settings.volc_resource_id
        self._endpoint = endpoint or settings.volc_endpoint
        self._system_prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT
        self._persona_context = persona_context
        self._memory_context = memory_context
        self._voice_profile_id = voice_profile_id or "default"
        self._audio_sample_rate = _AUDIO_SAMPLE_RATE
        self._audio_format = _AUDIO_FORMAT

    # ------------------------------------------------------------------
    # RealtimeVoiceProvider protocol
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return "volc_realtime"

    @property
    def supports_interrupt(self) -> bool:
        return True

    @property
    def supports_text_delta(self) -> bool:
        return True

    async def run(
        self,
        ws_send_json,
        ws_send_bytes,
        ws_receive,
        *,
        memory_user_id: str = "anonymous",
        memory_session_id: str | None = None,
    ) -> None:
        del memory_user_id, memory_session_id  # Volc path uses its own session model; reserved for API parity.
        if not self._app_id or not self._access_token:
            await ws_send_json({
                "type": "error",
                "msg": (
                    "Volcengine credentials not configured. "
                    "Set COMPANION_VOLC_APP_ID and COMPANION_VOLC_ACCESS_TOKEN."
                ),
            })
            return

        headers = {
            "X-Api-App-Key": self._app_id,
            "X-Api-Access-Key": self._access_token,
            "X-Api-Resource-Id": self._resource_id,
            "X-Api-Connect-Id": uuid.uuid4().hex,
        }

        logger.info(
            "volc_realtime.connecting",
            endpoint=self._endpoint,
            headers=_redact_headers(headers),
        )
        try:
            async with websockets.connect(
                self._endpoint,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                logger.info("volc_realtime.connected")
                await self._send_start_connection(ws)
                await asyncio.wait_for(self._wait_connection_started(ws), timeout=10.0)

                await self._send_start_session(ws)
                await asyncio.wait_for(self._wait_session_started(ws), timeout=10.0)
                await ws_send_json({"type": "ready"})

                interrupt_event = asyncio.Event()

                recv_task = asyncio.create_task(
                    self._receive_loop(ws, ws_send_json, ws_send_bytes, interrupt_event)
                )
                send_task = asyncio.create_task(
                    self._send_loop(ws, ws_receive, interrupt_event, ws_send_json)
                )

                done, pending = await asyncio.wait(
                    [recv_task, send_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await t

                await self._send_finish_session(ws)
        except TimeoutError:
            logger.error("volc_realtime.timeout")
            await ws_send_json({"type": "error", "msg": "Connection timeout"})
        except ConnectionClosed as exc:
            logger.info("volc_realtime.connection_closed", code=exc.code)
        except Exception as exc:
            logger.exception("volc_realtime.error", error=str(exc))
            with contextlib.suppress(Exception):
                await ws_send_json({"type": "error", "msg": str(exc)})

    # ------------------------------------------------------------------
    # Connection & session lifecycle
    # ------------------------------------------------------------------

    async def _send_start_connection(self, ws) -> None:
        msg = _build_event_payload(EVENT_START_CONNECTION, {})
        await ws.send(msg)

    async def _wait_connection_started(self, ws) -> None:
        while True:
            raw = await ws.recv()
            if isinstance(raw, bytes):
                parsed = _parse_response(raw)
                eid = parsed.get("_event_id")
                if eid == EVENT_CONNECTION_STARTED:
                    logger.info("volc_realtime.connection_started")
                    return
                if eid == EVENT_CONNECTION_FAILED:
                    msg = parsed.get("message", str(parsed)[:300])
                    raise RuntimeError(f"Connection failed: {msg}")

    async def _send_start_session(self, ws) -> None:
        voice_id = resolve_voice("volc_realtime", self._voice_profile_id, strict=False)
        if not voice_id:
            voice_id = "default"
        session_config = {
            "asr": {"language": "zh"},
            "tts": {
                "voice": voice_id,
                "audio_config": {
                    "format": self._audio_format,
                    "sample_rate": self._audio_sample_rate,
                    # channel (singular) is the official field per
                    # https://www.volcengine.com/docs/6561/1594356.
                    # channels (plural) is a fallback for older API versions.
                    # Remove the wrong one once integration confirms which one works.
                    "channel": _AUDIO_CHANNELS,
                    "channels": _AUDIO_CHANNELS,
                    "bit_depth": _AUDIO_BIT_DEPTH,
                },
            },
            "llm": {"system_prompt": self._system_prompt},
        }
        msg = _build_event_payload(EVENT_START_SESSION, session_config)
        await ws.send(msg)
        logger.info(
            "volc_realtime.session_config_sent",
            asr_lang="zh",
            tts_voice=voice_id,
            profile_id=self._voice_profile_id,
            audio_format=self._audio_format,
        )

    async def _wait_session_started(self, ws) -> None:
        while True:
            raw = await ws.recv()
            if isinstance(raw, bytes):
                parsed = _parse_response(raw)
                eid = parsed.get("_event_id")
                if eid == EVENT_SESSION_STARTED:
                    logger.info("volc_realtime.session_started")
                    return
                if eid == EVENT_SESSION_FAILED:
                    msg = parsed.get("message", str(parsed)[:300])
                    raise RuntimeError(f"Session failed: {msg}")

    async def _send_finish_session(self, ws) -> None:
        with contextlib.suppress(Exception):
            await ws.send(_build_finish_session())

    # ------------------------------------------------------------------
    # Send loop: user audio → Volc
    # ------------------------------------------------------------------

    async def _send_loop(self, ws, ws_receive, interrupt_event: asyncio.Event, ws_send_json) -> None:
        try:
            while True:
                msg = await ws_receive()
                if msg["type"] == "disconnect":
                    return
                if msg["type"] == "binary":
                    await ws.send(_build_audio_payload(msg["data"]))
                elif msg["type"] == "text":
                    try:
                        ctrl = json.loads(msg["data"])
                    except Exception:
                        continue
                    ctype = ctrl.get("type")
                    if ctype == "speech_end":
                        await ws.send(_build_audio_payload(b"", is_last=True))
                    elif ctype == "interrupt":
                        await self._handle_interrupt(ws, interrupt_event, ws_send_json)
                    elif ctype == "reset":
                        with contextlib.suppress(Exception):
                            await ws.send(_build_finish_session())
        except Exception as exc:
            logger.info("volc_realtime.send_loop_done", error=str(exc))

    async def _handle_interrupt(self, ws, interrupt_event: asyncio.Event, ws_send_json) -> None:
        """Cancel the current Volc turn and notify the frontend.

        Sends EVENT_FINISH_SESSION to tell Volc to stop the current
        response, sets the interrupt event so the receive loop clears
        partial text, and emits ``interrupted`` to the frontend.
        """
        logger.info("volc_realtime.interrupt")
        with contextlib.suppress(Exception):
            await ws.send(_build_finish_session())
        interrupt_event.set()
        await ws_send_json({"type": "interrupted"})

    # ------------------------------------------------------------------
    # Receive loop: Volc events → unified events
    # ------------------------------------------------------------------

    async def _receive_loop(
        self, ws, ws_send_json, ws_send_bytes, interrupt_event: asyncio.Event
    ) -> None:
        partial_text = ""
        try:
            async for raw in ws:
                if not isinstance(raw, bytes):
                    continue

                if interrupt_event.is_set():
                    partial_text = ""
                    interrupt_event.clear()

                parsed = _parse_response(raw)
                eid = parsed.get("_event_id")
                serialization = parsed.get("_serialization", JSON_SERIALIZATION)

                if eid == EVENT_ASR_RESPONSE:
                    word = parsed.get("word") or parsed.get("text") or ""
                    if word:
                        await ws_send_json({"type": "user_transcript_delta", "text": word})
                        partial_text += word

                elif eid == EVENT_ASR_ENDED:
                    if partial_text:
                        await ws_send_json({
                            "type": "user_transcript_final",
                            "text": partial_text.strip(),
                        })
                        partial_text = ""

                elif eid == EVENT_CHAT_RESPONSE:
                    token = parsed.get("word") or parsed.get("text") or ""
                    if token:
                        await ws_send_json({"type": "assistant_text_delta", "text": token})

                elif eid == EVENT_TTS_SENTENCE_START:
                    sentence = parsed.get("text") or parsed.get("sentence") or ""
                    if sentence:
                        await ws_send_json({
                            "type": "assistant_sentence_start",
                            "text": sentence,
                            "sample_rate": self._audio_sample_rate,
                            "audio_format": self._audio_format,
                        })

                elif eid == EVENT_TTS_RESPONSE:
                    await self._handle_tts_response(parsed, serialization, ws_send_bytes)

                elif eid == EVENT_TTS_ENDED:
                    await ws_send_json({"type": "assistant_audio_done"})

                elif eid == EVENT_CHAT_ENDED:
                    pass

                elif eid == EVENT_SESSION_FAILED:
                    await ws_send_json({
                        "type": "error",
                        "msg": parsed.get("message", "Session failed"),
                    })

        except ConnectionClosed:
            pass
        except Exception as exc:
            logger.exception("volc_realtime.receive_error", error=str(exc))
            await ws_send_json({"type": "error", "msg": str(exc)})

    async def _handle_tts_response(
        self,
        parsed: dict[str, Any],
        serialization: int,
        ws_send_bytes,
    ) -> None:
        """Extract audio bytes from a TTSResponse frame and forward to the client.

        JSON path:
            Tries ``parsed["audio"]`` → ``parsed.get("data")`` →
            ``parsed.get("payload_msg", {}).get("audio")``.
            Base64 decoding failures are logged.

        NO_SERIALIZATION path:
            The raw payload is PCM audio.  If ``VOLC_TTS_STRIP_SENTENCE_ID=1``
            and the first 4 bytes look like a small uint32, strips them.
        """
        if serialization == JSON_SERIALIZATION:
            audio_data = (
                parsed.get("audio")
                or parsed.get("data")
                or (parsed.get("payload_msg") or {}).get("audio")
            )
            if not audio_data:
                return
            if isinstance(audio_data, str):
                try:
                    audio_data = base64.b64decode(audio_data)
                except Exception:
                    logger.warning("volc_realtime.tts_b64_decode_failed")
                    return
            if isinstance(audio_data, bytes) and audio_data:
                await ws_send_bytes(audio_data)
        else:
            raw = parsed.get("_raw_payload")
            if not raw or not isinstance(raw, bytes) or not raw:
                return
            if _STRIP_SENTENCE_ID and len(raw) >= 4:
                maybe_id = struct.unpack(">I", raw[:4])[0]
                if maybe_id < 0x10000:
                    raw = raw[4:]
            await ws_send_bytes(raw)


__all__ = [
    "VolcRealtimeProvider",
    "_make_header",
    "_build_event_payload",
    "_build_audio_payload",
    "_parse_response",
    "_redact_headers",
]
