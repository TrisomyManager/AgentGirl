"""Cloud realtime voice provider.

Uses cloud ASR (SiliconFlow / OpenAI / DashScope) → LLM stream → cloud
TTS (SiliconFlow / OpenAI / DashScope / Fish Audio). No local models
downloaded.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import uuid

import structlog

from voice_layer.asr import ASRClient
from voice_layer.providers.realtime._llm_stream import (
    DEFAULT_SYSTEM_PROMPT as _SYSTEM_PROMPT,
    stream_llm as _stream_llm,
)
from voice_layer.tts import TTSClient

logger = structlog.get_logger("voice_layer.providers.cloud_realtime")

_SENTENCE_END = re.compile(r"[。！？!?\n]|[，、,;；](?=.{6,})")


class CloudRealtimeProvider:
    """Cloud ASR + LLM + Cloud TTS pipeline as a RealtimeVoiceProvider."""

    @property
    def provider_name(self) -> str:
        return "cloud"

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
        session = _CloudSession(
            ws_send_json,
            ws_send_bytes,
            memory_user_id=memory_user_id,
            memory_session_id=memory_session_id,
        )
        await session.run(ws_receive)


class _CloudSession:
    def __init__(
        self,
        send_json,
        send_bytes,
        *,
        memory_user_id: str = "anonymous",
        memory_session_id: str | None = None,
    ) -> None:
        self._send_json = send_json
        self._send_bytes = send_bytes
        self._memory_user_id = (memory_user_id or "anonymous").strip() or "anonymous"
        self._memory_session_id = (memory_session_id or "").strip() or f"realtime-{uuid.uuid4()}"
        self._pcm_buffer = bytearray()
        self._current_turn_task: asyncio.Task | None = None
        self._history: list[dict[str, str]] = []
        self._closed = False
        self._asr: ASRClient | None = None
        self._tts: TTSClient | None = None

    async def run(self, ws_receive) -> None:
        try:
            self._asr = ASRClient()
            self._tts = TTSClient()
        except Exception as exc:
            logger.warning("cloud_realtime.init_failed", error=str(exc))
            await self._send_json({"type": "error", "msg": str(exc)})
            return

        logger.info(
            "cloud_realtime.session_start",
            asr_provider=self._asr.provider,
            asr_model=self._asr.default_model,
            tts_provider=self._tts.provider,
        )
        await self._send_json({"type": "ready"})

        try:
            while not self._closed:
                msg = await ws_receive()
                if msg["type"] == "disconnect":
                    break
                if msg["type"] == "binary":
                    self._pcm_buffer.extend(msg["data"])
                elif msg["type"] == "text":
                    try:
                        payload = json.loads(msg["data"])
                    except Exception:
                        logger.warning("cloud_realtime.bad_control", raw=str(msg["data"])[:200])
                        continue
                    ctype = payload.get("type")
                    if ctype == "start":
                        self._pcm_buffer.clear()
                        if isinstance(payload.get("user_id"), str) and payload["user_id"].strip():
                            self._memory_user_id = payload["user_id"].strip()
                        if isinstance(payload.get("session_id"), str) and payload["session_id"].strip():
                            self._memory_session_id = payload["session_id"].strip()
                        await self._send_json({"type": "ready"})
                    elif ctype == "ping":
                        await self._send_json({"type": "pong"})
                    elif ctype == "speech_end":
                        await self._on_speech_end()
                    elif ctype == "interrupt":
                        await self._on_interrupt()
                    elif ctype == "reset":
                        self._history.clear()
                        self._pcm_buffer.clear()
                        await self._cancel_turn()
                        await self._send_json({"type": "ready"})
        except Exception as exc:
            logger.exception("cloud_realtime.error", error=str(exc))
        finally:
            self._closed = True
            await self._cancel_turn()
            with contextlib.suppress(Exception):
                if self._asr:
                    await self._asr.close()
            with contextlib.suppress(Exception):
                if self._tts:
                    await self._tts.close()

    async def _on_speech_end(self) -> None:
        if not self._pcm_buffer:
            return
        audio = bytes(self._pcm_buffer)
        self._pcm_buffer.clear()
        await self._cancel_turn()
        self._current_turn_task = asyncio.create_task(self._run_turn(audio))

    async def _on_interrupt(self) -> None:
        await self._cancel_turn()
        self._pcm_buffer.clear()
        await self._send_json({"type": "interrupted"})

    async def _cancel_turn(self) -> None:
        if self._current_turn_task and not self._current_turn_task.done():
            self._current_turn_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._current_turn_task
        self._current_turn_task = None

    async def _run_turn(self, audio_pcm: bytes) -> None:
        try:
            logger.info("cloud_realtime.asr.start", pcm_len=len(audio_pcm))
            transcript = await self._asr.transcribe_pcm(audio_pcm, sample_rate=16000)
            transcript = transcript.strip()
            logger.info("cloud_realtime.asr.done", text=transcript)
            if not transcript:
                await self._send_json({"type": "user_transcript_final", "text": ""})
                return
            await self._send_json({"type": "user_transcript_final", "text": transcript})

            self._history.append({"role": "user", "content": transcript})

            assistant_full: list[str] = []
            sentence_buf: list[str] = []

            async for token in _stream_llm(self._history):
                assistant_full.append(token)
                sentence_buf.append(token)
                await self._send_json({"type": "assistant_text_delta", "text": token})

                joined = "".join(sentence_buf)
                m = _SENTENCE_END.search(joined)
                if m:
                    sentence = joined[: m.end()].strip()
                    rest = joined[m.end() :]
                    sentence_buf = [rest] if rest else []
                    if sentence:
                        await self._send_json({
                            "type": "assistant_sentence_start",
                            "text": sentence,
                            "provider": "cloud",
                            "audio_format": "pcm",
                            "sample_rate": 16000,
                        })
                        await self._speak(sentence)

            tail = "".join(sentence_buf).strip()
            if tail:
                await self._send_json({
                    "type": "assistant_sentence_start",
                    "text": tail,
                    "provider": "cloud",
                    "audio_format": "pcm",
                    "sample_rate": 16000,
                })
                await self._speak(tail)

            self._history.append({"role": "assistant", "content": "".join(assistant_full)})
            assistant_text = "".join(assistant_full).strip()
            if transcript and assistant_text:
                from voice_layer.realtime_memory_sync import schedule_realtime_turn_memory_sync

                schedule_realtime_turn_memory_sync(
                    user_id=self._memory_user_id,
                    session_id=self._memory_session_id,
                    user_message=transcript,
                    assistant_message=assistant_text,
                )
        except asyncio.CancelledError:
            logger.info("cloud_realtime.turn_cancelled")
            raise
        except Exception as exc:
            logger.exception("cloud_realtime.turn_error", error=str(exc))
            await self._send_json({"type": "error", "msg": str(exc)})

    async def _speak(self, sentence: str) -> None:
        chunks_sent = 0
        try:
            async for chunk in self._tts.synthesize_pcm_stream(sentence, sample_rate=16000):
                if self._closed:
                    return
                await self._send_bytes(chunk)
                chunks_sent += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("cloud_realtime.speak_failed", error=str(exc))
        if chunks_sent > 0:
            await self._send_json({"type": "assistant_audio_done"})


__all__ = ["CloudRealtimeProvider"]
