"""safety_guard P1-B 单元测试."""

from __future__ import annotations

import re

import pytest

from safety_guard import (
    SafetyCategory,
    SafetyGuard,
    SafetyLevel,
    SafetyRule,
    default_guard,
    safe_fallback_reply,
)


def test_clean_text_allowed() -> None:
    v = default_guard.check_input("今天天气真不错")
    assert v.allowed is True
    assert v.level == SafetyLevel.ALLOW
    assert v.matched_terms == ()
    assert v.pii_hits == ()


def test_block_term_blocks() -> None:
    v = default_guard.check_input("我想自杀")
    assert v.blocked is True
    assert v.allowed is False
    assert "自杀" in v.matched_terms
    assert "input_blocked" in v.reason


def test_warn_term_passes_with_flag() -> None:
    v = default_guard.check_input("最近有点抑郁")
    assert v.allowed is True
    assert v.level == SafetyLevel.WARN
    assert "抑郁" in v.matched_terms


def test_pii_email_detected_as_warn() -> None:
    v = default_guard.check_input("我邮箱是 me@example.com")
    assert v.allowed is True
    assert v.level == SafetyLevel.WARN
    assert "email" in v.pii_hits


def test_pii_phone_cn_detected() -> None:
    v = default_guard.check_input("电话 13812345678")
    assert v.level == SafetyLevel.WARN
    assert "phone_cn" in v.pii_hits


def test_check_output_uses_output_source() -> None:
    v = default_guard.check_output("自杀")
    assert v.blocked
    assert v.reason.startswith("output_")


def test_custom_rule_block() -> None:
    guard = SafetyGuard(
        custom_rules=[
            SafetyRule(name="forbidden_brand", pattern=re.compile(r"BadCorp", re.IGNORECASE)),
        ]
    )
    v = guard.check_input("BadCorp 的产品")
    assert v.blocked
    assert "forbidden_brand" in v.matched_terms


def test_safe_fallback_reply_self_harm_specialized() -> None:
    verdict = default_guard.check_input("我想自杀")
    assert verdict.category == SafetyCategory.SELF_HARM
    text = safe_fallback_reply(verdict)
    assert "陪着你" in text and "现在安全吗" in text
    assert not re.search(r"\d{3}[-\d]{5,}", text)


@pytest.mark.parametrize("text", ["炸药配方", "制毒"])
def test_general_block_is_not_misreported_as_a_self_harm_crisis(text):
    verdict = default_guard.check_input(text)
    assert verdict.blocked and verdict.category == SafetyCategory.GENERAL
    reply = safe_fallback_reply(verdict)
    assert "现在安全吗" not in reply and "伤害自己" not in reply
    assert "伤害行为" in reply
    assert safe_fallback_reply("input_blocked") == reply


def test_empty_text_allows() -> None:
    v = default_guard.check_input("")
    assert v.allowed is True
    assert v.level == SafetyLevel.ALLOW


def test_overlapping_block_wins_over_warn() -> None:
    v = default_guard.check_input("我想自杀，我抑郁了")
    # block 优先级高于 warn
    assert v.blocked
    assert v.level == SafetyLevel.BLOCK
