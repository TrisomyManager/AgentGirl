"""Volcengine end-to-end realtime voice provider.

Connects to Volcengine (火山引擎) realtime dialogue API via WebSocket,
handles the binary protocol, and normalizes vendor events into the
project's unified realtime event model.

References:
    https://www.volcengine.com/docs/6561/1594356?lang=zh

Interrupt semantics:
    Uses ClientInterrupt (515) in push_to_talk mode; the session stays open.

Audio format:
    Requests pcm_s16le at 24 kHz, mono. The browser receives signed int16 PCM.
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
import websockets.asyncio.client as websockets
from websockets.exceptions import ConnectionClosed

from shared_runtime.config import get_settings
from shared_runtime.voice_runtime_config import get_effective_voice_config
from voice_layer.conversation_context import load_conversation_context, segment_presentation
from voice_layer.realtime_memory_sync import schedule_realtime_turn_memory_sync
from voice_layer.resolver import resolve_voice
from voice_layer.text_policy import CheckedText, check_text, policy_enabled, requires_complete_output

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
_AUDIO_FORMAT = "pcm_s16le"
_AUDIO_SAMPLE_RATE = 24000
_AUDIO_CHANNELS = 1
_AUDIO_BIT_DEPTH = 16

# Feature flag: strip leading sentence_id from NO_SERIALIZATION TTS payloads.
# Set VOLC_TTS_STRIP_SENTENCE_ID=1 to enable.  Default off (0).
_STRIP_SENTENCE_ID = os.getenv("VOLC_TTS_STRIP_SENTENCE_ID", "0") == "1"


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy with sensitive header values redacted for logging."""
    sensitive = {"x-api-access-key", "x-api-app-key", "x-api-app-id", "x-api-key"}
    return {
        k: "****"
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


def _build_event_payload(
    event_id: int, data: dict[str, Any] | None = None, session_id: str = "",
) -> bytes:
    header = _make_header(flags=HAS_EVENT_ID)
    body = gzip.compress(json.dumps(data or {}, ensure_ascii=False).encode("utf-8"))
    optional = struct.pack(">I", event_id)
    if event_id >= 100:
        sid = session_id.encode("utf-8")
        optional += struct.pack(">I", len(sid)) + sid
    return header + optional + struct.pack(">I", len(body)) + body


def _build_audio_payload(audio_bytes: bytes, is_last: bool = False, session_id: str = "") -> bytes:
    if is_last:
        return _build_event_payload(400, {}, session_id)
    header = _make_header(message_type=AUDIO_ONLY_REQUEST, flags=HAS_EVENT_ID,
                          serialization=NO_SERIALIZATION, compression=NO_COMPRESSION)
    sid = session_id.encode("utf-8")
    return (header + struct.pack(">I", EVENT_TASK_REQUEST) + struct.pack(">I", len(sid)) + sid
            + struct.pack(">I", len(audio_bytes)) + audio_bytes)


def _build_finish_session(session_id: str = "") -> bytes:
    return _build_event_payload(EVENT_FINISH_SESSION, {}, session_id)


def _parse_response(message: bytes) -> dict[str, Any]:
    """Decode optional event/session/sequence/error fields before payload size."""
    if len(message) < 8:
        return {"_parse_error": "message too short", "_raw_len": len(message)}
    msg_type, flags = message[1] >> 4, message[1] & 0x0F
    serialization, compression = message[2] >> 4, message[2] & 0x0F
    offset = (message[0] & 0x0F) * 4
    result: dict[str, Any] = {"_msg_type": msg_type, "_flags": flags,
                              "_serialization": serialization, "_compression": compression, "_event_id": None}

    def read_int() -> int:
        nonlocal offset
        if offset + 4 > len(message):
            raise ValueError("payload truncated")
        value = struct.unpack(">I", message[offset:offset + 4])[0]
        offset += 4
        return value

    def read_blob() -> bytes:
        nonlocal offset
        size = read_int()
        if offset + size > len(message):
            raise ValueError("payload truncated")
        value = message[offset:offset + size]
        offset += size
        return value

    try:
        if offset < 4:
            raise ValueError("invalid header size")
        if msg_type == 0x0F:
            result["_error_code"] = read_int()
        if flags & 1:
            result["_sequence"] = read_int()
        if flags & HAS_EVENT_ID:
            event_id = read_int()
            result["_event_id"] = event_id
            if event_id >= 100:
                result["_session_id"] = read_blob().decode("utf-8")
            elif event_id in (50, 51, 52):
                result["_connect_id"] = read_blob().decode("utf-8")
        payload = read_blob()
        if compression == GZIP_COMPRESSION:
            payload = gzip.decompress(payload)
        if serialization == JSON_SERIALIZATION:
            parsed = json.loads(payload.decode("utf-8"))
            if isinstance(parsed, dict):
                result.update(parsed)
            else:
                result["_json_value"] = parsed
        else:
            result["_raw_payload"] = payload
    except (ValueError, OSError, EOFError, struct.error) as exc:
        result["_parse_error"] = str(exc)
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
        rt = get_effective_voice_config()
        self._api_key = rt.get("volc_api_key") or ""
        self._model = rt.get("volc_model") or "1.2.1.1"
        self._voice_id = rt.get("volc_voice_id") or "zh_female_xiaohe_jupiter_bigtts"
        self._session_id = str(uuid.uuid4())
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
        self._memory_user_id = "anonymous"
        self._memory_session_id = f"realtime-{uuid.uuid4()}"
        self._conversation_context = None

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
        if not self._api_key and not (self._app_id and self._access_token):
            await ws_send_json({
                "type": "error",
                "msg": (
                    "Volcengine credentials not configured. "
                    "请在设置页填写豆包语音 API Key，或设置 COMPANION_VOLC_API_KEY。"
                ),
            })
            return

        self._memory_user_id = (memory_user_id or "anonymous").strip() or "anonymous"
        self._memory_session_id = (memory_session_id or "").strip() or f"realtime-{uuid.uuid4()}"
        try:
            self._conversation_context = await load_conversation_context(
                user_id=self._memory_user_id, session_id=self._memory_session_id, turn_id=uuid.uuid4().hex,
            )
        except RuntimeError as exc:
            await ws_send_json({"type": "error", "msg": str(exc)})
            return

        headers = {
            "X-Api-Resource-Id": self._resource_id,
            "X-Api-Connect-Id": uuid.uuid4().hex,
        }

        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        else:
            headers.update({"X-Api-App-ID": self._app_id, "X-Api-Access-Key": self._access_token,
                            "X-Api-App-Key": "PlgvMymc7f3tQnJ6"})

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

                await self._run_session_loops(ws, ws_send_json, ws_send_bytes, ws_receive, interrupt_event)

                await self._send_finish_session(ws)
        except TimeoutError:
            logger.error("volc_realtime.timeout")
            await ws_send_json({"type": "error", "msg": "Connection timeout"})
        except ConnectionClosed as exc:
            logger.info("volc_realtime.connection_closed", code=exc.code)
        except Exception as exc:
            logger.warning("volc_realtime.error", reason=type(exc).__name__)
            with contextlib.suppress(Exception):
                await ws_send_json({"type": "error", "msg": "实时语音连接失败，请检查服务配置后重试。"})

    # ------------------------------------------------------------------
    # Connection & session lifecycle
    # ------------------------------------------------------------------

    async def _run_session_loops(self, ws, send_json, send_bytes, receive, interrupted):
        tasks = [
            asyncio.create_task(self._receive_loop(ws, send_json, send_bytes, interrupted)),
            asyncio.create_task(self._send_loop(ws, receive, interrupted, send_json)),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

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
                if eid == EVENT_CONNECTION_FAILED or parsed.get("_error_code") or parsed.get("_parse_error"):
                    msg = parsed.get("message", str(parsed)[:300])
                    raise RuntimeError(f"Connection failed: {msg}")

    async def _send_start_session(self, ws) -> None:
        voice_id = self._voice_id if self._voice_profile_id == "default" else resolve_voice(
            "volc_realtime", self._voice_profile_id, strict=True,
        )
        base_prompt = self._conversation_context.system_prompt if self._conversation_context else self._system_prompt
        prompt = "\n".join(filter(None, [base_prompt, self._persona_context, self._memory_context]))
        dialog = {"extra": {"model": self._model, "input_mod": "push_to_talk"}}
        if self._model.startswith("2."):
            dialog["character_manifest"] = prompt
        else:
            dialog.update(system_role=prompt)
        session_config = {
            "asr": {"audio_info": {"format": "pcm", "sample_rate": 16000, "channel": 1}},
            "tts": {"speaker": voice_id, "audio_config": {
                "format": self._audio_format, "sample_rate": self._audio_sample_rate, "channel": 1,
            }},
            "dialog": dialog,
        }
        msg = _build_event_payload(EVENT_START_SESSION, session_config, self._session_id)
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
                if eid == EVENT_SESSION_FAILED or parsed.get("_error_code") or parsed.get("_parse_error"):
                    msg = parsed.get("message", str(parsed)[:300])
                    raise RuntimeError(f"Session failed: {msg}")

    async def _send_finish_session(self, ws) -> None:
        with contextlib.suppress(Exception):
            await ws.send(_build_finish_session(self._session_id))

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
                    await ws.send(_build_audio_payload(msg["data"], session_id=self._session_id))
                elif msg["type"] == "text":
                    try:
                        ctrl = json.loads(msg["data"])
                    except Exception:
                        continue
                    ctype = ctrl.get("type")
                    if ctype == "start":
                        # Native conversation state is already bound at connection time.
                        # Rebinding it would expose one user's vendor history to another.
                        if (ctrl.get("user_id", self._memory_user_id) != self._memory_user_id or
                                ctrl.get("session_id", self._memory_session_id) != self._memory_session_id):
                            await ws_send_json({"type": "error", "msg": "用户或会话已改变，请重新连接通话。"})
                            return
                    elif ctype == "ping":
                        await ws_send_json({"type": "pong"})
                    elif ctype == "speech_end":
                        await ws.send(_build_audio_payload(b"", is_last=True, session_id=self._session_id))
                    elif ctype == "interrupt":
                        await self._handle_interrupt(ws, interrupt_event, ws_send_json)
                    elif ctype == "reset":
                        interrupt_event.set()
                        await ws.send(_build_finish_session(self._session_id))
                        self._session_id = str(uuid.uuid4())
                        await self._send_start_session(ws)
        except Exception as exc:
            logger.info("volc_realtime.send_loop_done", error=str(exc))

    async def _handle_interrupt(self, ws, interrupt_event: asyncio.Event, ws_send_json) -> None:
        """Cancel the current Volc turn and notify the frontend.

        Sends ClientInterrupt without ending the session, clears partial
        text, and emits ``interrupted`` to the frontend.
        """
        logger.info("volc_realtime.interrupt")
        with contextlib.suppress(Exception):
            await ws.send(_build_event_payload(515, {}, self._session_id))
        interrupt_event.set()
        await ws_send_json({"type": "interrupted"})

    # ------------------------------------------------------------------
    # Receive loop: Volc events → unified events
    # ------------------------------------------------------------------

    async def _receive_loop(
        self, ws, ws_send_json, ws_send_bytes, interrupt_event: asyncio.Event
    ) -> None:
        partial_text = ""
        drop_output = False
        user_text = ""
        assistant_text = ""
        spoken_sentences = []
        turn_id = ""
        text_done = audio_done = audio_seen = False
        audio_announced = False
        presentation_index = -1
        guarded = policy_enabled()
        pending_audio = bytearray()
        caption_approved = False
        sent_audio_end = False

        async def reject(decision):
            nonlocal drop_output, user_text, assistant_text, audio_announced
            original_user = user_text
            drop_output = True
            user_text = ""
            pending_audio.clear()
            with contextlib.suppress(Exception):
                await ws.send(_build_event_payload(515, {}, self._session_id))
            await ws_send_json({"type": "interrupted"})
            assistant_text = decision.text
            await ws_send_json({"type": "assistant_text_delta", "text": decision.text})
            await ws_send_json({"type": "assistant_text_done"})
            # Unsafe vendor audio is never reused to speak a replacement.
            from voice_layer.tts import TTSClient
            tts = TTSClient()
            produced = False
            audio_announced = False
            try:
                async with asyncio.timeout(10), contextlib.aclosing(tts.synthesize_pcm_stream(decision.text, sample_rate=self._audio_sample_rate)) as source:
                    async for chunk in source:
                        if interrupt_event.is_set():
                            return
                        if not produced:
                            await announce_audio(decision.text)
                        await ws_send_bytes(chunk)
                        produced = True
            except Exception:
                await ws_send_json({"type": "error", "code": "safe_reply_audio_unavailable", "recoverable": True,
                                    "msg": "本轮回复已显示为文字，语音暂时不可用。"})
            finally:
                await tts.close()
            await ws_send_json({"type": "assistant_audio_done", "final": True})
            await ws_send_json({"type": "turn_done", "turn_id": turn_id, "content_filtered": True})
            if original_user and produced:
                schedule_realtime_turn_memory_sync(user_id=self._memory_user_id, session_id=self._memory_session_id,
                    user_message=original_user, assistant_message=decision.text, turn_id=turn_id,
                    conversation_context=self._conversation_context, content_filtered=True)

        async def announce_audio(sentence=""):
            nonlocal audio_announced, presentation_index, turn_id
            audio_announced = True
            presentation_index = min(255, presentation_index + 1)
            turn_id = turn_id or uuid.uuid4().hex
            await ws_send_json({
                "type": "assistant_sentence_start", "text": sentence,
                "sample_rate": self._audio_sample_rate, "audio_format": "pcm",
                "provider": self.provider_name,
                "avatar_timeline": segment_presentation(self._conversation_context, turn_id, presentation_index),
            })

        async def complete_turn():
            nonlocal user_text, audio_seen, sent_audio_end
            if pending_audio:
                if not text_done:
                    return
                if not assistant_text:
                    await reject(CheckedText("语音缺少可检查的文字，本轮已停止播放，请重试。", True, "unverified_audio"))
                    return
                checked = await check_text(assistant_text, source="output")
                if checked.blocked:
                    await reject(checked)
                    return
                if not audio_announced:
                    await announce_audio(assistant_text)
                # Coalesce buffered PCM without exceeding the client's frame limit.
                for offset in range(0, len(pending_audio), 256 * 1024):
                    await ws_send_bytes(bytes(pending_audio[offset:offset + 256 * 1024]))
                pending_audio.clear()
                audio_seen = True
            if audio_done and not sent_audio_end:
                await ws_send_json({"type": "assistant_audio_done", "final": True})
                sent_audio_end = True
            if not (user_text and text_done and audio_done and audio_seen):
                return
            reply = assistant_text or "".join(spoken_sentences)
            if reply:
                schedule_realtime_turn_memory_sync(
                    user_id=self._memory_user_id, session_id=self._memory_session_id,
                    user_message=user_text, assistant_message=reply, turn_id=turn_id,
                    conversation_context=self._conversation_context,
                )
                user_text = ""  # duplicate vendor end events cannot commit twice
                await ws_send_json({"type": "turn_done", "turn_id": turn_id})

        try:
            iterator = ws.__aiter__()
            while True:
                try:
                    async with asyncio.timeout(2 if guarded and pending_audio and audio_done and not text_done else None):
                        raw = await anext(iterator)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    await reject(CheckedText("语音文字未完整返回，本轮已停止播放，请重新连接后重试。", True, "unverified_audio"))
                    break
                if not isinstance(raw, bytes):
                    continue

                if interrupt_event.is_set():
                    partial_text = ""
                    user_text = ""
                    drop_output = True
                    interrupt_event.clear()
                    pending_audio.clear()
                    caption_approved = False

                parsed = _parse_response(raw)
                eid = parsed.get("_event_id")
                serialization = parsed.get("_serialization", JSON_SERIALIZATION)

                if parsed.get("_parse_error") or parsed.get("_error_code"):
                    raise RuntimeError(parsed.get("error") or parsed.get("_parse_error") or "火山语音协议错误")
                if drop_output and eid in {EVENT_CHAT_RESPONSE, EVENT_CHAT_ENDED, EVENT_TTS_SENTENCE_START,
                                           EVENT_TTS_RESPONSE, EVENT_TTS_ENDED}:
                    continue
                if eid == 450:
                    partial_text = ""
                    user_text = ""
                    drop_output = True
                    pending_audio.clear()
                    caption_approved = False
                    await ws_send_json({"type": "interrupted"})
                elif eid == EVENT_ASR_RESPONSE:
                    results = parsed.get("results") or []
                    word = (results[-1].get("text", "") if results else
                            parsed.get("word") or parsed.get("text") or "")
                    if word:
                        delta = word[len(partial_text):] if word.startswith(partial_text) else word
                        if delta:
                            await ws_send_json({"type": "user_transcript_delta", "text": delta})
                        partial_text = word

                elif eid == EVENT_ASR_ENDED:
                    drop_output = guarded and not bool(partial_text.strip())
                    if partial_text:
                        user_text = partial_text.strip()
                        assistant_text = ""
                        spoken_sentences = []
                        turn_id = uuid.uuid4().hex
                        text_done = audio_done = audio_seen = False
                        audio_announced = False
                        presentation_index = -1
                        caption_approved = sent_audio_end = False
                        pending_audio.clear()
                        await ws_send_json({
                            "type": "user_transcript_final",
                            "text": partial_text.strip(),
                        })
                        partial_text = ""
                        decision = await check_text(user_text, source="input")
                        if decision.blocked:
                            await reject(decision)

                elif eid == EVENT_CHAT_RESPONSE:
                    token = parsed.get("content") or parsed.get("word") or parsed.get("text") or ""
                    if token:
                        checked = await check_text(assistant_text + token, source="output")
                        if checked.blocked:
                            await reject(checked)
                            continue
                        assistant_text = (assistant_text + token)[:16000]
                        if not guarded:
                            await ws_send_json({"type": "assistant_text_delta", "text": token})

                elif eid == EVENT_TTS_SENTENCE_START:
                    sentence = parsed.get("text") or parsed.get("sentence") or ""
                    caption_approved = False
                    if guarded:
                        if not sentence:
                            continue
                        checked = await check_text("".join(spoken_sentences) + sentence, source="output")
                        if checked.blocked:
                            await reject(checked)
                            continue
                        caption_approved = not requires_complete_output()
                    if sentence:
                        if guarded or len(spoken_sentences) < 100:
                            spoken_sentences.append(sentence if guarded else sentence[:2000])
                    # O2 may provide an empty TTS-start event or omit it entirely.
                    if not guarded or caption_approved:
                        await announce_audio(sentence)

                elif eid == EVENT_TTS_RESPONSE:
                    async def forward_audio(chunk):
                        nonlocal audio_seen
                        if guarded and (pending_audio or (not caption_approved and (not text_done or not assistant_text))):
                            if len(pending_audio) + len(chunk) > self._audio_sample_rate * 2 * 30:
                                await reject(CheckedText("待检查的语音过长，本轮已停止，请分成短句后重试。", True, "audio_too_long"))
                                return
                            pending_audio.extend(chunk)
                            if text_done:
                                await complete_turn()
                            return
                        if not audio_announced:
                            await announce_audio()
                        await ws_send_bytes(chunk)
                        audio_seen = True

                    await self._handle_tts_response(parsed, serialization, forward_audio)

                elif eid == EVENT_TTS_ENDED:
                    audio_done = True
                    await complete_turn()

                elif eid == EVENT_CHAT_ENDED:
                    if guarded:
                        checked = await check_text(assistant_text, source="output")
                        if checked.blocked:
                            await reject(checked)
                            continue
                        if assistant_text:
                            await ws_send_json({"type": "assistant_text_delta", "text": assistant_text})
                    text_done = True
                    await ws_send_json({"type": "assistant_text_done"})
                    await complete_turn()

                elif eid == 351:
                    # Sentence-end events remove the previous caption's approval.
                    caption_approved = False

                elif eid == EVENT_SESSION_FAILED or parsed.get("_error_code") or parsed.get("_parse_error"):
                    await ws_send_json({
                        "type": "error",
                        "msg": parsed.get("message", "Session failed"),
                    })

            if pending_audio and not drop_output:
                await reject(CheckedText("语音缺少完整文字，本轮已停止播放，请重试。", True, "unverified_audio"))
        except ConnectionClosed:
            pass
        except Exception as exc:
            logger.warning("volc_realtime.receive_error", reason=type(exc).__name__)
            await ws_send_json({"type": "error", "msg": "实时语音连接中断，请重新连接。"})

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
