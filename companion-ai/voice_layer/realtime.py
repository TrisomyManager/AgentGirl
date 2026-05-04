"""Real-time voice pipeline over WebSocket.

Doubao-style voice call flow:
    client PCM (16kHz mono Int16) → faster-whisper ASR → DashScope LLM stream
    → sentence-level piper TTS → client PCM playback (with barge-in support)

Protocol
--------
Client → Server (JSON text frames):
    {"type": "start"}                     # session ready, prepare to listen
    {"type": "speech_end"}                # VAD detected end of utterance
    {"type": "interrupt"}                 # user spoke during AI playback
    {"type": "ping"}

Client → Server (binary frames):
    raw 16-bit PCM mono @16kHz audio chunks (only while user speaking)

Server → Client (JSON):
    {"type": "transcript", "text": "..."}        # final ASR result
    {"type": "llm_token", "text": "..."}         # incremental LLM token
    {"type": "llm_done"}                          # LLM finished
    {"type": "tts_start", "sample_rate": 22050}  # before first audio chunk
    {"type": "tts_done"}                          # all TTS audio sent
    {"type": "turn_done"}                         # full turn complete; ready for next
    {"type": "error", "msg": "..."}
    {"type": "pong"}

Server → Client (binary):
    raw 16-bit PCM mono @22050Hz audio chunks (piper output)
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import AsyncIterator, Optional

import httpx
import structlog
from fastapi import WebSocket, WebSocketDisconnect

from shared.llm_client import get_runtime_llm_config
from shared.config import get_settings
from voice_layer import local_asr, local_tts

logger = structlog.get_logger("voice_layer.realtime")

# Punctuation that ends a sentence — we flush TTS at these boundaries.
_SENTENCE_END = re.compile(r"[。！？!?\n]|[，、,;；](?=.{6,})")
_SYSTEM_PROMPT = (
    "你叫小暖，是一个温柔体贴、富有共情力的 AI 陪伴助手。"
    "用户正在通过语音和你对话，请用自然、口语化的中文短句回复，"
    "每次回复控制在 1-3 句话以内，避免书面语和列表格式。"
)


class RealtimeSession:
    """One WebSocket session: handles state machine for a single call."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.pcm_buffer = bytearray()
        self.current_turn_task: Optional[asyncio.Task] = None
        self.history: list[dict[str, str]] = []  # [{role, content}]
        self.closed = False

    async def run(self) -> None:
        await self.ws.accept()
        logger.info("realtime.connected")
        try:
            local_asr.warmup()
            local_tts.warmup()
        except Exception as exc:
            logger.warning("realtime.warmup_failed", error=str(exc))

        try:
            while not self.closed:
                msg = await self.ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if "bytes" in msg and msg["bytes"] is not None:
                    self.pcm_buffer.extend(msg["bytes"])
                elif "text" in msg and msg["text"] is not None:
                    await self._handle_control(msg["text"])
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.exception("realtime.error", error=str(exc))
        finally:
            self.closed = True
            await self._cancel_turn()
            logger.info("realtime.disconnected")

    # ------------------------------------------------------------------
    # Control messages
    # ------------------------------------------------------------------

    async def _handle_control(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except Exception:
            logger.warning("realtime.bad_control", raw=raw[:200])
            return

        ctype = payload.get("type")
        if ctype == "start":
            self.pcm_buffer.clear()
            await self._send_json({"type": "ready"})
        elif ctype == "ping":
            await self._send_json({"type": "pong"})
        elif ctype == "speech_end":
            await self._on_speech_end()
        elif ctype == "interrupt":
            await self._on_interrupt()
        elif ctype == "reset":
            self.history.clear()
            self.pcm_buffer.clear()
            await self._cancel_turn()
            await self._send_json({"type": "ready"})
        else:
            logger.info("realtime.unknown_control", type=ctype)

    async def _on_speech_end(self) -> None:
        """User finished speaking — kick off transcribe → LLM → TTS pipeline."""
        if not self.pcm_buffer:
            return
        audio = bytes(self.pcm_buffer)
        self.pcm_buffer.clear()
        await self._cancel_turn()  # safety: cancel any prior incomplete turn
        self.current_turn_task = asyncio.create_task(self._run_turn(audio))

    async def _on_interrupt(self) -> None:
        """Cancel any in-flight LLM + TTS so user can speak."""
        await self._cancel_turn()
        self.pcm_buffer.clear()
        await self._send_json({"type": "interrupted"})

    async def _cancel_turn(self) -> None:
        if self.current_turn_task and not self.current_turn_task.done():
            self.current_turn_task.cancel()
            try:
                await self.current_turn_task
            except (asyncio.CancelledError, Exception):
                pass
        self.current_turn_task = None

    # ------------------------------------------------------------------
    # Turn pipeline
    # ------------------------------------------------------------------

    async def _run_turn(self, audio_pcm: bytes) -> None:
        try:
            # 1. ASR
            transcript = await local_asr.transcribe_pcm(audio_pcm, sample_rate=16000)
            transcript = transcript.strip()
            logger.info("realtime.transcript", text=transcript)
            if not transcript:
                await self._send_json({"type": "transcript", "text": ""})
                await self._send_json({"type": "turn_done"})
                return
            await self._send_json({"type": "transcript", "text": transcript})

            self.history.append({"role": "user", "content": transcript})

            # 2. LLM stream + 3. sentence-level TTS in pipeline
            assistant_full = []
            sentence_buf = []
            tts_tasks: list[asyncio.Task] = []

            async for token in self._stream_llm(self.history):
                assistant_full.append(token)
                sentence_buf.append(token)
                await self._send_json({"type": "llm_token", "text": token})

                joined = "".join(sentence_buf)
                # Find a sentence boundary
                m = _SENTENCE_END.search(joined)
                if m:
                    sentence = joined[: m.end()].strip()
                    rest = joined[m.end():]
                    sentence_buf = [rest] if rest else []
                    if sentence:
                        tts_tasks.append(asyncio.create_task(self._speak(sentence)))

            await self._send_json({"type": "llm_done"})

            # Flush remaining sentence tail if any
            tail = "".join(sentence_buf).strip()
            if tail:
                tts_tasks.append(asyncio.create_task(self._speak(tail)))

            # Wait all TTS sequentially in the order created so audio order is correct.
            # We already started them in order; await sequentially without re-starting.
            for t in tts_tasks:
                try:
                    await t
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("realtime.tts_task_failed", error=str(exc))

            self.history.append({"role": "assistant", "content": "".join(assistant_full)})
            await self._send_json({"type": "turn_done"})
        except asyncio.CancelledError:
            logger.info("realtime.turn_cancelled")
            raise
        except Exception as exc:
            logger.exception("realtime.turn_error", error=str(exc))
            await self._send_json({"type": "error", "msg": str(exc)})

    # ------------------------------------------------------------------
    # LLM streaming via OpenAI-compatible chat completions
    # ------------------------------------------------------------------

    async def _stream_llm(self, history: list[dict[str, str]]) -> AsyncIterator[str]:
        settings = get_settings()
        rt = get_runtime_llm_config()

        api_key = rt.get("openai_api_key") or settings.openai_api_key
        base_url = (
            rt.get("openai_base_url") or settings.openai_base_url or "https://api.openai.com/v1"
        ).rstrip("/")
        model = rt.get("default_model") or settings.default_llm_model or "qwen-turbo"

        if not api_key:
            yield "（语音模型已就绪，但还没有配置 LLM 接口。请在设置中填入大模型 API Key。）"
            return

        messages = [{"role": "system", "content": _SYSTEM_PROMPT}] + history
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": 0.7,
            "max_tokens": 512,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        url = f"{base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    err_body = await resp.aread()
                    raise RuntimeError(f"LLM HTTP {resp.status_code}: {err_body.decode('utf-8', errors='ignore')}")
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except Exception:
                        continue
                    delta = obj.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content")
                    if token:
                        yield token

    # ------------------------------------------------------------------
    # TTS streaming
    # ------------------------------------------------------------------

    async def _speak(self, sentence: str) -> None:
        """Synthesize one sentence via piper and stream PCM chunks to client."""
        sample_rate = local_tts.get_sample_rate()
        await self._send_json({"type": "tts_start", "sample_rate": sample_rate, "text": sentence})
        try:
            async for chunk in local_tts.synthesize_pcm_chunks(sentence):
                if self.closed:
                    return
                await self.ws.send_bytes(chunk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("realtime.speak_failed", error=str(exc))
        await self._send_json({"type": "tts_done"})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _send_json(self, obj: dict) -> None:
        if self.closed:
            return
        try:
            await self.ws.send_text(json.dumps(obj, ensure_ascii=False))
        except Exception:
            self.closed = True


async def realtime_handler(websocket: WebSocket) -> None:
    """Entry point used by the FastAPI route."""
    session = RealtimeSession(websocket)
    await session.run()
