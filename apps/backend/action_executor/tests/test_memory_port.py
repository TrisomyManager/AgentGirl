import os
import subprocess
import sys
from pathlib import Path

from action_executor.handlers import query_memory
from action_executor.memory_port import get_memory_reader, set_memory_reader


async def test_reader_failure_is_not_reported_as_empty_memory():
    class Reader:
        async def recall(self, **kwargs):
            raise RuntimeError("synthetic-private-diagnostic")

    previous = get_memory_reader()
    set_memory_reader(Reader())
    try:
        result = await query_memory({"user_id": "port-test", "query": "记忆"})
    finally:
        set_memory_reader(previous)
    assert not result.ok and result.data == {"error": "memory_unavailable"}
    assert "synthetic-private-diagnostic" not in str(result)


def test_memory_tools_run_with_an_external_reader_and_no_memory_package():
    script = """
import asyncio
import importlib.abc
import sys
class NoMemory(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "memory_system" or fullname.startswith("memory_system."):
            raise AssertionError("Action module must not load a memory implementation")
sys.meta_path.insert(0, NoMemory())
from action_executor.handlers import query_memory
from action_executor.memory_port import set_memory_reader
class Reader:
    async def recall(self, **kwargs):
        return [{"content":"external host fact", "importance":0.7}]
    async def list_recent(self, **kwargs):
        return []
    async def working(self, **kwargs):
        return None
set_memory_reader(Reader())
result=asyncio.run(query_memory({"user_id":"external", "query":"fact"}))
assert result.ok and "external host fact" in result.message
assert "memory_system" not in sys.modules
"""
    env = {**os.environ, "COMPANION_LITE_MODE": "true"}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr[-1000:]
