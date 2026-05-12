"""onboarding P1-B 单元测试."""

from __future__ import annotations

import pytest

from onboarding import (
    OnboardingFlow,
    OnboardingResult,
    OnboardingStep,
    apply_to_profile,
    default_steps,
)
from user_profile import InMemoryUserProfileStore


def test_default_steps_count() -> None:
    steps = default_steps()
    assert len(steps) == 4
    assert {s.key for s in steps} == {"role", "nickname", "locale", "greeting"}


def test_flow_normal_path() -> None:
    flow = OnboardingFlow(user_id="u1")
    assert not flow.is_complete
    assert flow.current_step().key == "role"

    flow.submit_answer("aria")
    assert flow.current_step().key == "nickname"
    assert flow.result.role_id == "aria"

    flow.submit_answer("阿正")
    assert flow.current_step().key == "locale"
    assert flow.result.nickname == "阿正"

    flow.submit_answer("zh-CN")
    assert flow.current_step().key == "greeting"
    assert flow.result.locale == "zh-CN"

    flow.submit_answer("最近想多读点书")
    assert flow.is_complete
    assert flow.current_step() is None
    assert flow.result.extras["initial_greeting"] == "最近想多读点书"
    assert flow.result.completed_steps == ["role", "nickname", "locale", "greeting"]


def test_flow_unknown_role_falls_back_to_default() -> None:
    flow = OnboardingFlow(user_id="u1")
    flow.submit_answer("nonexistent_role")
    assert flow.result.role_id == "default"


def test_flow_skip_optional_step() -> None:
    flow = OnboardingFlow(user_id="u1")
    flow.submit_answer("default")  # role
    flow.skip()  # skip nickname
    assert flow.current_step().key == "locale"
    assert flow.result.nickname is None
    assert "nickname" in flow.result.completed_steps


def test_flow_skip_required_step_raises() -> None:
    flow = OnboardingFlow(user_id="u1")
    with pytest.raises(ValueError):
        flow.skip()  # role is required


def test_flow_invalid_locale_falls_back_to_zh_cn() -> None:
    flow = OnboardingFlow(user_id="u1")
    flow.submit_answer("default")
    flow.submit_answer("Bob")
    flow.submit_answer("fr-FR")
    assert flow.result.locale == "zh-CN"


@pytest.mark.asyncio
async def test_apply_to_profile_writes_snapshot() -> None:
    store = InMemoryUserProfileStore()
    result = OnboardingResult(
        user_id="u1",
        role_id="aria",
        nickname="阿正",
        locale="zh-CN",
        completed_steps=["role", "nickname"],
        extras={"initial_greeting": "你好"},
    )
    await apply_to_profile(result, store)
    snap = await store.get("u1")
    assert snap is not None
    assert snap.display_name == "阿正"
    assert snap.preferences["role_id"] == "aria"
    assert snap.metadata["onboarding_completed_steps"] == ["role", "nickname"]
    assert snap.metadata["initial_greeting"] == "你好"
