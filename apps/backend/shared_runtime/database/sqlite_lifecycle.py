"""Finish SQLite worker operations before propagating request cancellation.

Cancelling aiosqlite while its worker is opening the file queues a stop callback
without awaiting it. The host must close the resulting connection before its
event loop can disappear; otherwise the worker may call a closed event loop.
Queries and closure also settle their worker commands; the host explicitly owns
and closes orphaned connections after draining work and disposing its pool.
"""

import asyncio
from threading import Thread

import aiosqlite

_connections: set = set()


async def _settle_worker(task):
    """Cancellation cannot leave a worker callback targeting an expired loop."""
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


async def drain_sqlite_connections():
    """Close checked-out leftovers after the host has drained work and disposed its pool."""
    for connection in tuple(_connections):
        await connection.close()


def _own_connection(connection, thread):
    execute = connection._execute
    close = connection.close

    async def execute_owned(*args, **kwargs):
        return await _settle_worker(asyncio.create_task(execute(*args, **kwargs)))

    async def close_owned():
        async def finish():
            try:
                await close()
            finally:
                await asyncio.to_thread(thread.join)
                _connections.discard(connection)

        await _settle_worker(asyncio.create_task(finish()))

    connection._execute = execute_owned
    connection.close = close_owned
    _connections.add(connection)
    return connection


async def open_sqlite_connection(*args, **kwargs):
    connection = aiosqlite.connect(*args, **kwargs)
    thread = connection if isinstance(connection, Thread) else connection._thread
    thread.daemon = True  # Match SQLAlchemy's default aiosqlite connector.
    connecting = asyncio.ensure_future(connection)
    try:
        result = await asyncio.shield(connecting)
        return _own_connection(result, thread)
    except asyncio.CancelledError:

        async def finish_and_close():
            try:
                connection = await connecting
            except Exception:
                pass
            else:
                await connection.close()
            finally:
                await asyncio.to_thread(thread.join)

        cleanup = asyncio.create_task(finish_and_close(), name="sqlite:cancelled-connect-cleanup")
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                continue
        cleanup.result()
        raise
    except Exception:
        await asyncio.to_thread(thread.join)
        raise
