"""Own asynchronous memory ingestion until host shutdown or explicit cancellation."""

import asyncio

import structlog

from shared_runtime.user_lifecycle import user_operation

logger = structlog.get_logger(__name__)
_tasks = {}


def submit_memory_task(coroutine, *, user_id):
    async def owned():
        try:
            async with user_operation(user_id):
                return await coroutine
        finally:
            if hasattr(coroutine, "close"):
                coroutine.close()

    task = asyncio.create_task(owned(), name="companion-memory-ingestion")
    _tasks[task] = user_id

    def completed(done):
        _tasks.pop(done, None)
        if hasattr(coroutine, "close"):
            coroutine.close()
        if not done.cancelled() and done.exception() is not None:
            logger.warning("memory.background_failed", reason=type(done.exception()).__name__)

    task.add_done_callback(completed)
    return task


async def drain_memory_tasks(*, timeout=5.0, user_id=None):
    """Wait briefly, then cancel and await cleanup before closing shared clients/SQL."""
    loop = asyncio.get_running_loop()
    tasks = [
        task
        for task, owner in tuple(_tasks.items())
        if task.get_loop() is loop and not task.done() and (user_id is None or owner == user_id)
    ]
    if not tasks:
        return 0
    _, pending = await asyncio.wait(tasks, timeout=max(0, timeout))
    for task in pending:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    return len(tasks)
