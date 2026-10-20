import asyncio
import sqlite3
import threading
import time

import aiosqlite
import pytest

from shared_runtime.database.sqlite_lifecycle import drain_sqlite_connections, open_sqlite_connection


async def test_cancelled_connect_finishes_and_closes_the_real_sqlite_worker(monkeypatch):
    opened, connector_started = [], threading.Event()
    original_connect = aiosqlite.connect

    def delayed(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        original_connector = connection._connector

        def connector():
            connector_started.set()
            time.sleep(0.04)
            db = original_connector()
            opened.append(db)
            return db

        connection._connector = connector
        return connection

    monkeypatch.setattr(aiosqlite, "connect", delayed)
    task = asyncio.create_task(open_sqlite_connection(":memory:", check_same_thread=False))
    await asyncio.to_thread(connector_started.wait)
    task.cancel()
    await asyncio.sleep(0.005)
    task.cancel()  # A second cancellation must not strand the cleanup task.
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")
    assert not [task for task in asyncio.all_tasks() if task.get_name() == "sqlite:cancelled-connect-cleanup"]


async def test_cancelled_query_finishes_worker_before_cancellation_reaches_the_host():
    connection = await open_sqlite_connection(":memory:", check_same_thread=False)
    started, finished = threading.Event(), threading.Event()

    def slow_query():
        started.set()
        time.sleep(0.04)
        finished.set()
        return 1

    await connection.create_function("slow_query", 0, slow_query)
    task = asyncio.create_task(connection.execute("SELECT slow_query()"))
    await asyncio.to_thread(started.wait)
    task.cancel()
    await asyncio.sleep(0.005)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()
    await connection.close()
    assert not connection._thread.is_alive()


async def test_host_shutdown_closes_an_orphaned_checked_out_connection():
    connection = await open_sqlite_connection(":memory:", check_same_thread=False)
    await connection.execute("SELECT 1")
    await drain_sqlite_connections()
    assert not connection._thread.is_alive()
    with pytest.raises(ValueError, match="no active connection"):
        await connection.execute("SELECT 1")
