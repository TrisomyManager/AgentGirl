from shared_contracts.models import MemoryCategory, MemoryEntry, MemoryRecallResult
from shared_runtime.prompt_engine import build_conversation_system_prompt


def test_long_recalled_content_and_graph_facts_have_separate_budgets_and_no_duplicates():
    memory = MemoryRecallResult(entries=[
        MemoryEntry(entry_id=str(index), user_id="u", category=MemoryCategory.FACT, content=content)
        for index, content in enumerate(["咖啡" * 2000, "咖啡" * 2000, "散步" * 1000])
    ], graph_facts=["事实" * 2000])
    prompt = build_conversation_system_prompt(persona=None, memory=memory)
    recall = prompt.split("【记忆片段】\n", 1)[1].split("【已知事实】", 1)[0]
    facts = prompt.split("【已知事实】\n", 1)[1].split("【可用能力】", 1)[0]
    assert len(recall) <= 1200 + 20
    assert len(facts) <= 600 + 20


def test_stable_profile_is_bounded_and_does_not_copy_arbitrary_settings():
    from types import SimpleNamespace

    from shared_runtime.prompt_engine import format_user_profile_memory

    snapshot = SimpleNamespace(display_name="阿明", preferences={
        "latest_like": "无糖咖啡", "preferred_tone": "简洁", "api_key": "do-not-inject",
        "role_id": "role", "interests": ["散步" * 1000],
    })
    text = format_user_profile_memory(snapshot)
    assert "阿明" in text and "无糖咖啡" in text
    assert "do-not-inject" not in text and len(text) <= 600
