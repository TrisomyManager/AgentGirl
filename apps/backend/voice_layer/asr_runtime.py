"""Per-operation ASR ownership with an optional host-supplied service factory."""

import asyncio
from collections.abc import Callable
from typing import Protocol

from starlette.requests import HTTPConnection

from shared_contracts.protocols import SpeechRecognizer

ASRFactory = Callable[[], SpeechRecognizer]


def new_recognizer(connection: HTTPConnection) -> SpeechRecognizer:
    factory = getattr(connection.app.state, "voice_asr_factory", None)
    if factory is None:
        from voice_layer.asr import ASRClient

        factory = ASRClient
    recognizer = factory()
    if not isinstance(recognizer, SpeechRecognizer):
        raise TypeError("Host ASR factory must return a SpeechRecognizer")
    return recognizer


class _AsyncCloseable(Protocol):
    async def close(self) -> None: ...


async def close_voice_resources(*resources: _AsyncCloseable | None) -> None:
    """A cancelled request still owns its service until cleanup has settled."""

    async def close():
        async with asyncio.timeout(10):
            results = await asyncio.gather(
                *(item.close() for item in resources if item is not None), return_exceptions=True
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result

    task = asyncio.create_task(close())
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    task.result()
    if cancelled:
        raise asyncio.CancelledError
