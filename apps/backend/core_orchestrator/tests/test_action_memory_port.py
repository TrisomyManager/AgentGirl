from uuid import uuid4

from action_executor.handlers import query_memory
from action_executor.memory_port import get_memory_reader, set_memory_reader
from core_orchestrator.runtime_hooks import ReferenceMemoryReader
from memory_system.vector_store import store_memory
from memory_system.working import get_working_memory
from shared_contracts.models import MemoryEntry
from shared_contracts.protocols import MemoryReader
from shared_runtime.config import get_settings
from shared_runtime.database import AsyncSessionLocal, init_database_schema


async def test_reference_reader_uses_actual_sql_and_preserves_session_ownership(monkeypatch):
    monkeypatch.setattr(get_settings(), "working_memory_llm_summary", False)
    monkeypatch.setattr(get_settings(), "working_memory_llm_digest", False)
    user, session_id = uuid4().hex, uuid4().hex
    await init_database_schema()
    async with AsyncSessionLocal() as session:
        await store_memory(
            session,
            MemoryEntry(
                entry_id="",
                user_id=user,
                category="fact",
                content="合成测试：我喜欢绿茶。",
                embedding=[0.0] * 1024,
            ),
            extracted={"entities": [], "relations": []},
        )
    await get_working_memory().observe_turn(session_id, uuid4().hex, "我叫小林。", "记住了。", user_id=user)
    reader = ReferenceMemoryReader()
    assert isinstance(reader, MemoryReader)
    previous = get_memory_reader()
    set_memory_reader(reader)
    try:
        result = await query_memory({"user_id": user, "session_id": session_id})
    finally:
        set_memory_reader(previous)
    assert result.ok and "绿茶" in result.message
    assert result.data["working_memory"]["turn_count"] == 1
    assert await reader.working(user_id=uuid4().hex, session_id=session_id) is None
