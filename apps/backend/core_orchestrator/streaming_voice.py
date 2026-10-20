"""Merge chat events and bounded, concurrently synthesized voice segments.

The source owns text/turn persistence; this adapter owns every synthesis task.
Failures affect only that segment, while ordered delivery prevents audio swaps.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass

import structlog

from avatar_runtime import build_avatar_timeline
from shared_runtime.text_segmenter import SentenceSegmenter

logger = structlog.get_logger(__name__)
Synthesize = Callable[[str, dict], Awaitable[dict]]


@dataclass
class _Job:
    seq: int
    text: str
    context: dict
    future: asyncio.Future


async def stream_voice_events(
    source: AsyncIterator[dict],
    synthesize: Synthesize,
    *,
    turn_id: str,
    concurrency: int = 2,
    min_chars: int = 8,
    max_chars: int = 80,
    timeout_seconds: float = 30,
    max_segments: int = 128,
) -> AsyncIterator[dict]:
    if not 1 <= concurrency <= 4 or not 1 <= max_segments <= 256:
        raise ValueError("Invalid streaming voice limits")
    segmenter = SentenceSegmenter(min_chars=min_chars, max_chars=max_chars)
    output: asyncio.Queue = asyncio.Queue(maxsize=32)
    work: asyncio.Queue = asyncio.Queue(maxsize=concurrency * 2)
    ordered: asyncio.Queue = asyncio.Queue(maxsize=concurrency * 2)
    slots = asyncio.Semaphore(concurrency * 2)
    context, segments, errors = {}, [], []
    done_event = None
    total = 0
    first_token_at = None
    first_audio = True
    truncated = False

    async def enqueue(sentence):
        nonlocal total, truncated
        if total >= max_segments:
            truncated = True
            return
        await slots.acquire()
        future = asyncio.get_running_loop().create_future()
        job = _Job(total, sentence, dict(context), future)
        total += 1
        await work.put(job)
        await ordered.put(job)

    async def produce():
        nonlocal done_event, first_token_at
        async with aclosing(source):
            async for event in source:
                if event.get("event") == "meta":
                    context.update(event.pop("_voice_context", {}))
                    event["voice_mode"] = "segmented"
                if event.get("event") == "done":
                    done_event = event
                    continue
                await output.put(event)
                if event.get("event") == "token":
                    if first_token_at is None:
                        first_token_at = time.monotonic()
                    for sentence in segmenter.feed(event.get("text", "")):
                        await enqueue(sentence)
        if tail := segmenter.flush():
            await enqueue(tail)
        for _ in range(concurrency):
            await work.put(None)
        await ordered.put(None)

    async def synthesize_worker():
        while (job := await work.get()) is not None:
            started = time.monotonic()
            try:
                async with asyncio.timeout(timeout_seconds):
                    result = await synthesize(job.text, job.context)
                url = result.get("audio_url") or result.get("voice_url")
                if not isinstance(url, str) or not url.strip():
                    raise ValueError("Empty segment audio URL")
                duration = result.get("duration_ms")
                duration = max(0, int(duration)) if duration is not None else None
                event = {
                    "event": "voice_segment",
                    "turn_id": turn_id,
                    "seq": job.seq,
                    "text": job.text,
                    "audio_url": url.strip(),
                    "duration_ms": duration,
                    "emotion": job.context.get("emotion_state"),
                    "avatar_timeline": build_avatar_timeline(
                        turn_id=turn_id, segment_seq=job.seq, duration_ms=duration,
                        emotion=job.context.get("emotion_state"),
                    ).model_dump(mode="json"),
                }
                logger.info(
                    "voice_segment_synthesized",
                    turn_id=turn_id,
                    seq=job.seq,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    text_len=len(job.text),
                )
            except Exception:
                # Do not echo upstream response bodies/URLs/credentials into SSE.
                event = {
                    "event": "voice_segment_error",
                    "turn_id": turn_id,
                    "seq": job.seq,
                    "error": "这一段语音暂时无法生成，文字回复仍可查看。",
                }
            job.future.set_result(event)

    async def deliver():
        nonlocal first_audio
        while (job := await ordered.get()) is not None:
            event = await job.future
            if event["event"] == "voice_segment":
                segments.append({key: value for key, value in event.items() if key != "event"})
                if first_audio:
                    first_audio = False
                    logger.info(
                        "stream_first_voice_segment",
                        turn_id=turn_id,
                        after_first_token_ms=int((time.monotonic() - first_token_at) * 1000)
                        if first_token_at
                        else None,
                    )
            else:
                errors.append(event)
            await output.put(event)
            slots.release()

    async def run():
        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(produce(), name=f"voice-text:{turn_id}")
                for index in range(concurrency):
                    group.create_task(synthesize_worker(), name=f"voice-synth:{turn_id}:{index}")
                group.create_task(deliver(), name=f"voice-deliver:{turn_id}")
            state = (done_event or {}).get("_state")
            duration = sum(item.get("duration_ms") or 0 for item in segments)
            if state is not None:
                state["voice_mode"] = "segmented" if total else None
                state["voice_segments"] = segments
                state["voice_duration_ms"] = duration if total else None
                if errors or truncated:
                    state["voice_error"] = "部分语音未能生成。" if segments else "语音暂时无法生成。"
                await output.put(
                    {
                        "event": "voice_done",
                        "turn_id": turn_id,
                        "segments": total,
                        "successful_segments": len(segments),
                        "total_duration_ms": duration,
                        "truncated": truncated,
                    }
                )
            if done_event:
                await output.put(done_event)
            await output.put({"_finished": True})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await output.put({"_failure": exc})

    worker = asyncio.create_task(run(), name=f"streaming-voice:{turn_id}")
    try:
        while True:
            event = await output.get()
            if "_finished" in event:
                break
            if "_failure" in event:
                raise event["_failure"]
            yield event
    finally:
        if not worker.done():
            worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
