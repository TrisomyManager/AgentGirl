"""safety_guard —— 内容安全与对话护栏 (P1-B 可用实现).

设计目标 (与 ARCHITECTURE.md / ADR-006 对齐):
- 业务模块在调用 LLM 之前/之后, 通过 ``check_input`` / ``check_output`` 过滤敏感内容
- 与具体模型解耦, 第三方宿主可注入自家审核服务
- 词库分级: BLOCK (硬阻断) / WARN (放行但标记) + 正则模式
- 输出端提供兜底安抚文案, 避免 LLM 偶发越界对用户体验造成冲击

P1-B 升级要点:
- ``SafetyLevel`` 枚举 + 默认词库分级
- 正则模式 (邮箱 / 手机号 / 身份证粗匹配) 用于 PII 提示
- ``safe_fallback_reply()`` 在 BLOCK 时给出温柔的兜底回复
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Pattern, Sequence, Tuple

__all__ = [
    "SafetyLevel",
    "SafetyVerdict",
    "SafetyRule",
    "SafetyGuard",
    "default_guard",
    "safe_fallback_reply",
]


class SafetyLevel(str, Enum):
    """安全裁决等级."""

    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


# ---------------------------------------------------------------------------
# Default rule sets
# ---------------------------------------------------------------------------

# BLOCK: 自伤 / 极端违法 / 露骨色情等硬红线
_DEFAULT_BLOCK_TERMS: tuple[str, ...] = (
    "自杀", "自残", "自我了断", "结束生命",
    "制毒", "贩毒",
    "炸药配方", "爆炸物制作",
    "儿童色情", "未成年色情",
)

# WARN: 情绪低落 / 暴力 / 仇恨等需要更温柔回应的词，放行但标记
_DEFAULT_WARN_TERMS: tuple[str, ...] = (
    "想死", "活不下去", "抑郁",
    "杀了", "弄死",
    "歧视", "仇恨",
)

# PII regex (粗匹配, 仅用于提示 / 脱敏)
_DEFAULT_PII_PATTERNS: tuple[tuple[str, str], ...] = (
    ("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("phone_cn", r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    ("idcard_cn", r"(?<!\d)\d{17}[\dXx](?!\d)"),
)


@dataclass(frozen=True)
class SafetyVerdict:
    """安全检查裁决结果.

    向后兼容: 旧字段 ``allowed`` / ``reason`` / ``matched_terms`` 保留.
    """

    allowed: bool
    reason: str = ""
    matched_terms: tuple[str, ...] = ()
    level: SafetyLevel = SafetyLevel.ALLOW
    pii_hits: tuple[str, ...] = ()

    @property
    def blocked(self) -> bool:
        return self.level == SafetyLevel.BLOCK

    @property
    def warned(self) -> bool:
        return self.level == SafetyLevel.WARN


@dataclass
class SafetyRule:
    """可注入的自定义规则."""

    name: str
    pattern: Pattern[str]
    level: SafetyLevel = SafetyLevel.BLOCK


def safe_fallback_reply(reason: str = "") -> str:
    """BLOCK 时的兜底文案 (温柔, 不评判)."""
    if "self_harm" in reason or "block" in reason:
        return (
            "我在这里，先深呼吸一下好吗？我有点担心你。"
            "如果有特别难受的念头，可以告诉我，我会陪着你；"
            "也可以拨打 24 小时心理援助热线 400-161-9995。"
        )
    return "这个话题我没办法陪你聊，不过你愿意的话，可以换个想说的事情，我都在听。"


class SafetyGuard:
    """关键词 + 正则护栏. 第三方宿主可继承覆盖 ``check_input`` / ``check_output``."""

    def __init__(
        self,
        block_terms: Iterable[str] | None = None,
        warn_terms: Iterable[str] | None = None,
        pii_patterns: Sequence[tuple[str, str]] | None = None,
        custom_rules: Iterable[SafetyRule] | None = None,
    ) -> None:
        self._block_terms = tuple(block_terms) if block_terms is not None else _DEFAULT_BLOCK_TERMS
        self._warn_terms = tuple(warn_terms) if warn_terms is not None else _DEFAULT_WARN_TERMS
        raw_patterns = pii_patterns if pii_patterns is not None else _DEFAULT_PII_PATTERNS
        self._pii_patterns: List[Tuple[str, Pattern[str]]] = [
            (name, re.compile(pat)) for name, pat in raw_patterns
        ]
        self._custom_rules: List[SafetyRule] = list(custom_rules or [])

    # ----- mutators -----------------------------------------------------

    def add_rule(self, rule: SafetyRule) -> None:
        self._custom_rules.append(rule)

    # ----- internal scan -----------------------------------------------

    def _scan_terms(self, text: str, terms: Sequence[str]) -> tuple[str, ...]:
        if not text:
            return ()
        return tuple(term for term in terms if term and term in text)

    def _scan_pii(self, text: str) -> tuple[str, ...]:
        if not text:
            return ()
        hits: List[str] = []
        for name, pattern in self._pii_patterns:
            if pattern.search(text):
                hits.append(name)
        return tuple(hits)

    def _scan_custom(self, text: str) -> List[SafetyRule]:
        return [rule for rule in self._custom_rules if rule.pattern.search(text or "")]

    # ----- public API ---------------------------------------------------

    def evaluate(self, text: str, *, source: str = "input") -> SafetyVerdict:
        block_hits = self._scan_terms(text, self._block_terms)
        warn_hits = self._scan_terms(text, self._warn_terms)
        pii_hits = self._scan_pii(text)
        custom_hits = self._scan_custom(text)

        for rule in custom_hits:
            if rule.level == SafetyLevel.BLOCK:
                return SafetyVerdict(
                    allowed=False,
                    reason=f"{source}_blocked:rule={rule.name}",
                    matched_terms=(rule.name,),
                    level=SafetyLevel.BLOCK,
                    pii_hits=pii_hits,
                )

        if block_hits:
            return SafetyVerdict(
                allowed=False,
                reason=f"{source}_blocked",
                matched_terms=block_hits,
                level=SafetyLevel.BLOCK,
                pii_hits=pii_hits,
            )

        warn_terms_hit = warn_hits + tuple(r.name for r in custom_hits if r.level == SafetyLevel.WARN)
        if warn_terms_hit:
            return SafetyVerdict(
                allowed=True,
                reason=f"{source}_warn",
                matched_terms=warn_terms_hit,
                level=SafetyLevel.WARN,
                pii_hits=pii_hits,
            )

        if pii_hits:
            return SafetyVerdict(
                allowed=True,
                reason=f"{source}_pii",
                matched_terms=(),
                level=SafetyLevel.WARN,
                pii_hits=pii_hits,
            )

        return SafetyVerdict(allowed=True, level=SafetyLevel.ALLOW)

    def check_input(self, text: str) -> SafetyVerdict:
        return self.evaluate(text, source="input")

    def check_output(self, text: str) -> SafetyVerdict:
        return self.evaluate(text, source="output")


default_guard = SafetyGuard()
