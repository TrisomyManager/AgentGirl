"""Ordered sentence TTS concurrent with token generation, with bounded backlog.

The parent owns both tasks. Cancellation/failure closes the token iterator and
waits for all child work before the caller acknowledges an interruption.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass, field

from shared_runtime.text_segmenter import SentenceSegmenter

DeltaCallback = Callable[[str], Awaitable[None]]
SentenceCallback = Callable[[str, int], Awaitable[None]]


@dataclass
class _AudioJob:
    text: str
    index: int
    frames: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=8))


async def stream_pcm_speech(
    tokens: AsyncIterator[str],
    *,
    synthesize: Callable[[str], AsyncIterator[bytes]],
    on_delta: DeltaCallback,
    on_start: SentenceCallback,
    on_audio: Callable[[bytes], Awaitable[None]],
    on_done: Callable[[int], Awaitable[None]],
    concurrency: int = 2,
    prefetch: int = 3,
    sentence_chars: int = 100,
    max_chars: int = 12000,
    sentence_timeout: float = 30,
    deadline_seconds: float = 120,
) -> str:
    """Prefetch PCM in bounded workers, while one sender preserves sentence order.

    Each in-flight sentence buffers at most eight 4 KiB frames. Synthesis can
    finish out of order; metadata and bytes always use the source order.
    """
    if not 1 <= concurrency <= 4 or not concurrency <= prefetch <= 16:
        raise ValueError("Invalid speech concurrency limits")
    slots = asyncio.Semaphore(prefetch)
    work: asyncio.Queue = asyncio.Queue(maxsize=prefetch)
    ordered: asyncio.Queue = asyncio.Queue(maxsize=prefetch)
    text = []

    async def produce():
        segmenter = SentenceSegmenter(max_chars=sentence_chars)
        size, index = 0, 0

        async def enqueue(sentence):
            nonlocal index
            await slots.acquire()
            job = _AudioJob(sentence, index)
            index += 1
            await work.put(job)
            await ordered.put(job)

        async with aclosing(tokens):
            async for token in tokens:
                size += len(token)
                if size > max_chars:
                    raise ValueError("Voice response exceeded the configured text limit")
                text.append(token)
                await on_delta(token)
                for sentence in segmenter.feed(token):
                    await enqueue(sentence)
            if tail := segmenter.flush():
                await enqueue(tail)
        for _ in range(concurrency):
            await work.put(None)
        await ordered.put(None)

    async def synthesize_worker():
        while (job := await work.get()) is not None:
            count = 0
            async with asyncio.timeout(sentence_timeout), aclosing(synthesize(job.text)) as source:
                async for chunk in source:
                    for offset in range(0, len(chunk), 4096):
                        await job.frames.put(chunk[offset : offset + 4096])
                        count += 1
            if not count:
                raise RuntimeError("语音服务没有返回音频。")
            await job.frames.put(None)

    async def deliver():
        while (job := await ordered.get()) is not None:
            await on_start(job.text, job.index)
            while (frame := await job.frames.get()) is not None:
                await on_audio(frame)
            await on_done(job.index)
            slots.release()

    async with asyncio.timeout(deadline_seconds), asyncio.TaskGroup() as group:
        group.create_task(produce(), name="speech:tokens")
        for index in range(concurrency):
            group.create_task(synthesize_worker(), name=f"speech:synthesize:{index}")
        group.create_task(deliver(), name="speech:ordered-output")
    return "".join(text)


async def stream_speech(
    tokens: AsyncIterator[str],
    *,
    on_delta: DeltaCallback,
    on_sentence: SentenceCallback,
    queue_size: int = 3,
    sentence_chars: int = 100,
    max_chars: int = 12000,
    sentence_timeout: float = 30,
    deadline_seconds: float = 120,
) -> str:
    if not 1 <= queue_size <= 16 or not 16 <= sentence_chars <= 500 or max_chars < sentence_chars:
        raise ValueError("Invalid speech buffering limits")
    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=queue_size)
    text: list[str] = []

    async def produce():
        segmenter = SentenceSegmenter(min_chars=1, max_chars=sentence_chars)
        size = 0
        async with aclosing(tokens):
            async for token in tokens:
                size += len(token)
                if size > max_chars:
                    raise ValueError("Voice response exceeded the configured text limit")
                text.append(token)
                await on_delta(token)
                for sentence in segmenter.feed(token):
                    await queue.put(sentence)
            tail = segmenter.flush()
            if tail:
                await queue.put(tail)
            await queue.put(None)

    async def consume():
        index = 0
        while (sentence := await queue.get()) is not None:
            async with asyncio.timeout(sentence_timeout):
                await on_sentence(sentence, index)
            index += 1

    async with asyncio.timeout(deadline_seconds):
        async with asyncio.TaskGroup() as group:
            group.create_task(produce(), name="speech:tokens")
            group.create_task(consume(), name="speech:tts")
    return "".join(text)
