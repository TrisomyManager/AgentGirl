"""Cloud realtime voice provider.

Uses cloud ASR (SiliconFlow / OpenAI / DashScope) → LLM stream → cloud
TTS (SiliconFlow / OpenAI / DashScope / Fish Audio). No local models
downloaded.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid

import structlog

from shared_contracts.protocols import SpeechRecognizer
from voice_layer.asr import ASRClient
from voice_layer.asr_runtime import ASRFactory, close_voice_resources
from voice_layer.conversation_context import load_conversation_context, segment_presentation
from voice_layer.providers.realtime._llm_stream import (
    stream_llm as _stream_llm,
)
from voice_layer.streaming_pipeline import stream_pcm_speech
from voice_layer.text_policy import check_text, checked_tokens, literal_text
from voice_layer.tts import TTSClient

logger = structlog.get_logger("voice_layer.providers.cloud_realtime")


class CloudRealtimeProvider:
    """Cloud ASR + LLM + Cloud TTS pipeline as a RealtimeVoiceProvider."""

    def __init__(self, *, asr_factory: ASRFactory | None = None):
        self.asr_factory = asr_factory

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
            asr_factory=self.asr_factory,
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
        asr_factory: ASRFactory | None = None,
    ) -> None:
        self._send_json = send_json
        self._send_bytes = send_bytes
        self._memory_user_id = (memory_user_id or "anonymous").strip() or "anonymous"
        self._memory_session_id = (memory_session_id or "").strip() or f"realtime-{uuid.uuid4()}"
        self._pcm_buffer = bytearray()
        self._audio_overflow = False
        self._current_turn_task: asyncio.Task | None = None
        self._history: list[dict[str, str]] = []
        self._closed = False
        self._asr: SpeechRecognizer | None = None
        self._asr_factory = asr_factory
        self._tts: TTSClient | None = None

    async def run(self, ws_receive) -> None:
        try:
            self._asr = (self._asr_factory or ASRClient)()
            self._tts = TTSClient()
        except Exception as exc:
            await close_voice_resources(self._asr, self._tts)
            logger.warning("cloud_realtime.init_failed", reason=type(exc).__name__)
            await self._send_json({"type": "error", "msg": "语音服务初始化失败，请检查宿主配置。"})
            return

        logger.info(
            "cloud_realtime.session_start",
            asr_provider=getattr(self._asr, "provider", "host"),
            asr_model=getattr(self._asr, "default_model", ""),
            tts_provider=self._tts.provider,
        )
        await self._send_json({"type": "ready"})

        try:
            while not self._closed:
                msg = await ws_receive()
                if msg["type"] == "disconnect":
                    break
                if msg["type"] == "binary":
                    if self._audio_overflow:
                        continue
                    if len(self._pcm_buffer) + len(msg["data"]) > 16000 * 2 * 60:
                        self._pcm_buffer.clear()
                        self._audio_overflow = True
                        await self._send_json({"type": "error", "code": "audio_too_long", "recoverable": True,
                                               "msg": "单次讲话超过一分钟，请分成较短的句子。"})
                        continue
                    self._pcm_buffer.extend(msg["data"])
                elif msg["type"] == "text":
                    try:
                        payload = json.loads(msg["data"])
                    except Exception:
                        logger.warning("cloud_realtime.bad_control", size=len(str(msg["data"])))
                        continue
                    ctype = payload.get("type")
                    if ctype == "start":
                        self._audio_overflow = False
                        await self._cancel_turn()
                        next_user = str(payload.get("user_id") or self._memory_user_id).strip()
                        next_session = str(payload.get("session_id") or self._memory_session_id).strip()
                        if (next_user, next_session) != (self._memory_user_id, self._memory_session_id):
                            self._history.clear()
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
                        self._audio_overflow = False
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
                await close_voice_resources(self._asr, self._tts)

    async def _on_speech_end(self) -> None:
        self._audio_overflow = False
        if not self._pcm_buffer:
            return
        audio = bytes(self._pcm_buffer)
        self._pcm_buffer.clear()
        await self._cancel_turn()
        self._current_turn_task = asyncio.create_task(self._run_turn(audio))

    async def _on_interrupt(self) -> None:
        self._audio_overflow = False
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
            logger.info("cloud_realtime.asr.done", text_len=len(transcript))
            if not transcript:
                await self._send_json({"type": "user_transcript_final", "text": ""})
                return
            await self._send_json({"type": "user_transcript_final", "text": transcript})

            turn_id = uuid.uuid4().hex
            decision = await check_text(transcript, source="input")
            filtered = decision.blocked

            def mark_filtered():
                nonlocal filtered
                filtered = True
            conversation_context = None if decision.blocked else await load_conversation_context(
                user_id=self._memory_user_id, session_id=self._memory_session_id,
                user_message=transcript, turn_id=turn_id,
            )
            options = {}
            if conversation_context is not None:
                options = {
                    "system_prompt": conversation_context.system_prompt,
                    "temperature": conversation_context.temperature,
                    "max_tokens": conversation_context.max_tokens,
                }
            self._history.append({"role": "user", "content": transcript})
            self._history = self._history[-24:]

            async def send_delta(token):
                await self._send_json({"type": "assistant_text_delta", "text": token})

            async def speak_sentence(sentence, index):
                await self._send_json({
                    "type": "assistant_sentence_start", "text": sentence,
                    "provider": "cloud", "audio_format": "pcm", "sample_rate": 16000,
                    "sentence_index": index,
                    "avatar_timeline": segment_presentation(conversation_context, turn_id, index),
                })

            async def sentence_done(index):
                await self._send_json({"type": "assistant_audio_done", "sentence_index": index})

            assistant_text = await stream_pcm_speech(
                checked_tokens(literal_text(decision.text) if decision.blocked else _stream_llm(self._history, **options), on_block=mark_filtered), on_delta=send_delta, on_start=speak_sentence,
                synthesize=lambda text: self._tts.synthesize_pcm_stream(text, sample_rate=16000),
                on_audio=self._send_bytes, on_done=sentence_done,
                concurrency=2,
            )
            self._history.append({"role": "assistant", "content": assistant_text})
            await self._send_json({"type": "turn_done"})
            if transcript and assistant_text:
                from voice_layer.realtime_memory_sync import schedule_realtime_turn_memory_sync

                schedule_realtime_turn_memory_sync(
                    user_id=self._memory_user_id,
                    session_id=self._memory_session_id,
                    user_message=transcript,
                    assistant_message=assistant_text,
                    turn_id=turn_id,
                    conversation_context=conversation_context,
                    content_filtered=filtered,
                )
        except asyncio.CancelledError:
            logger.info("cloud_realtime.turn_cancelled")
            raise
        except Exception as exc:
            logger.exception("cloud_realtime.turn_error", error=str(exc))
            await self._send_json({"type": "error", "msg": "语音输出中断，请检查语音设置或稍后再试。"})

    async def _speak(self, sentence: str) -> None:
        chunks_sent = 0
        try:
            async with contextlib.aclosing(self._tts.synthesize_pcm_stream(sentence, sample_rate=16000)) as chunks:
                async for chunk in chunks:
                    if self._closed:
                        return
                    await self._send_bytes(chunk)
                    chunks_sent += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("cloud_realtime.speak_failed", error=str(exc))
            raise RuntimeError("语音合成失败。") from exc
        if not chunks_sent:
            raise RuntimeError("语音服务没有返回音频。")
        await self._send_json({"type": "assistant_audio_done"})


__all__ = ["CloudRealtimeProvider"]
