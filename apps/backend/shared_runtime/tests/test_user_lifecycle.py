import asyncio
from uuid import uuid4

import pytest

from shared_runtime.user_lifecycle import (
    StaleUserOperation,
    UserBusyError,
    assert_user_context,
    erase_user_work,
    user_operation,
)


async def test_erasure_waits_for_owned_cleanup_and_invalidates_delayed_descendants():
    user = uuid4().hex
    started, cleaned, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    descendants = []

    async def late():
        await release.wait()
        assert_user_context()

    async def worker():
        async with user_operation(user):
            descendants.append(asyncio.create_task(late()))
            started.set()
            try:
                await asyncio.Future()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

    task = asyncio.create_task(worker())
    await started.wait()
    async with erase_user_work(user):
        assert cleaned.is_set()
        with pytest.raises(StaleUserOperation):
            async with user_operation(user):
                pytest.fail("new work entered an erasure barrier")
    assert task.cancelled()
    release.set()
    with pytest.raises(StaleUserOperation):
        await descendants[0]
    async with user_operation(user):
        assert_user_context()  # explicitly new work can start cleanly


async def test_uncooperative_worker_prevents_deletion_until_it_finishes():
    user = uuid4().hex
    started, finish = asyncio.Event(), asyncio.Event()

    async def worker():
        async with user_operation(user):
            started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                await finish.wait()

    task = asyncio.create_task(worker())
    await started.wait()
    with pytest.raises(UserBusyError):
        async with erase_user_work(user, timeout=0.01):
            pytest.fail("erasure continued before worker cleanup")
    with pytest.raises(StaleUserOperation):
        async with user_operation(user):
            pytest.fail("failed cancellation must leave ingress blocked")
    finish.set()
    await asyncio.gather(task, return_exceptions=True)
    async with erase_user_work(user):
        pass
    async with user_operation(user):
        assert_user_context()
