"""Shutdown awaits background ingestion and its asynchronous cleanup."""

import asyncio

from core_orchestrator.memory_tasks import drain_memory_tasks, submit_memory_task


async def test_timeout_cancellation_waits_for_cleanup_and_only_targets_the_requested_user():
    started, cleaned, other_started = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def ingestion():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.set()

    async def other_user():
        other_started.set()
        await asyncio.Event().wait()

    first = submit_memory_task(ingestion(), user_id="first")
    other = submit_memory_task(other_user(), user_id="other")
    await started.wait()
    await other_started.wait()
    assert await drain_memory_tasks(timeout=0, user_id="first") == 1
    assert first.cancelled() and cleaned.is_set()
    assert not other.done()
    await drain_memory_tasks(timeout=0)
    assert other.cancelled()


async def test_completed_writes_finish_without_cancellation_before_shutdown_returns():
    completed = []

    async def ingestion():
        await asyncio.sleep(0)
        completed.append("saved")

    task = submit_memory_task(ingestion(), user_id="user")
    await drain_memory_tasks(timeout=1)
    assert completed == ["saved"] and not task.cancelled()
