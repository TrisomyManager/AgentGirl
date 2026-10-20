"""Project-root pytest config.

Sets COMPANION_LITE_MODE before any test imports so memory_system / shared_runtime.database
modules pick up SQLite-friendly branches at import time. Also clears the
@lru_cache on get_settings() in case anything was imported earlier.
"""

import asyncio
import os
import tempfile

os.environ.setdefault("COMPANION_LITE_MODE", "true")
os.environ["COMPANION_WORKING_MEMORY_COMPRESSION_USE_LLM"] = "false"
os.environ["COMPANION_REACTION_USE_LLM"] = "false"
os.environ["COMPANION_INTENT_ROUTER_USE_LLM"] = "false"
_test_database_dir = tempfile.TemporaryDirectory(prefix="companion-tests-", ignore_cleanup_errors=True)
os.environ["COMPANION_LITE_DATABASE_URL"] = (
    "sqlite+aiosqlite:///" + _test_database_dir.name.replace("\\", "/") + "/tests.db"
)

from shared_runtime.config import get_settings  # noqa: E402

get_settings.cache_clear()

# Defensive: if memory_system.* or shared_runtime.database were already imported
# (e.g. via plugin auto-import), refresh their module-level `settings` ref.
import sys  # noqa: E402
import pytest  # noqa: E402

for _mod_name in ("memory_system.db", "memory_system.vector_store", "shared_runtime.database"):
    _mod = sys.modules.get(_mod_name)
    if _mod is not None and hasattr(_mod, "settings"):
        _mod.settings = get_settings()


@pytest.fixture(autouse=True)
async def drain_reference_host_tasks():
    """Direct SDK tests also own their spawned work until the event loop closes."""
    yield
    voice_module = sys.modules.get("voice_layer.realtime_memory_sync")
    if voice_module is not None:
        await voice_module.drain_memory_sync()
    module = sys.modules.get("core_orchestrator.memory_tasks")
    if module is not None:
        await module.drain_memory_tasks(timeout=0)
    from shared_runtime.database import engine
    from shared_runtime.database.sqlite_lifecycle import drain_sqlite_connections

    await engine.dispose()
    await drain_sqlite_connections()


def pytest_sessionfinish(session, exitstatus):
    """Release SQLite handles before Windows removes the isolated test directory."""
    from shared_runtime.database import engine

    asyncio.run(engine.dispose())
    _test_database_dir.cleanup()
