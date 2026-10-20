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
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from re import Pattern

__all__ = [
    "SafetyLevel",
    "SafetyCategory",
    "SafetyVerdict",
    "SafetyRule",
    "SafetyGuard",
    "default_guard",
    "safe_fallback_reply",
]


class SafetyLevel(str, Enum):  # noqa: UP042 -- preserve SDK enum string representation
    """安全裁决等级."""

    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


class SafetyCategory(str, Enum):  # noqa: UP042
    GENERAL = "general"
    SELF_HARM = "self_harm"
    CUSTOM = "custom"
    CONTACT = "unverified_contact"


# ---------------------------------------------------------------------------
# Default rule sets
# ---------------------------------------------------------------------------

# BLOCK: 自伤 / 极端违法 / 露骨色情等硬红线
_DEFAULT_BLOCK_TERMS: tuple[str, ...] = (
    "自杀",
    "自残",
    "自我了断",
    "结束生命",
    "制毒",
    "贩毒",
    "炸药配方",
    "爆炸物制作",
    "儿童色情",
    "未成年色情",
)

# WARN: 情绪低落 / 暴力 / 仇恨等需要更温柔回应的词，放行但标记
_DEFAULT_WARN_TERMS: tuple[str, ...] = (
    "想死",
    "活不下去",
    "抑郁",
    "杀了",
    "弄死",
    "歧视",
    "仇恨",
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
    category: SafetyCategory = SafetyCategory.GENERAL

    @property
    def blocked(self) -> bool:
        return not self.allowed or self.level == SafetyLevel.BLOCK

    @property
    def warned(self) -> bool:
        return self.level == SafetyLevel.WARN


@dataclass
class SafetyRule:
    """可注入的自定义规则."""

    name: str
    pattern: Pattern[str]
    level: SafetyLevel = SafetyLevel.BLOCK
    category: SafetyCategory = SafetyCategory.CUSTOM


def safe_fallback_reply(reason: str | SafetyVerdict = "") -> str:
    """Use an explicit category; a generic block is not evidence of a crisis."""
    category = reason.category if isinstance(reason, SafetyVerdict) else reason
    if isinstance(reason, SafetyVerdict) and reason.reason.endswith("_too_large"):
        return "内容过长，暂时无法完成检查，请分成较短的段落。"
    if category == SafetyCategory.SELF_HARM:
        return (
            "听起来你现在很难受，我会陪着你。你现在安全吗？"
            "如果有马上伤害自己的危险，请先远离可能伤到自己的东西，"
            "联系一个能到你身边的人，或当地的紧急救援。"
        )
    if category == SafetyCategory.CONTACT:
        return "这条联系信息尚未核实，请通过当地官方渠道确认适用的联系方式。"
    return "我不能协助实施这类伤害行为。你可以说明想解决的问题，我们一起找安全的办法。"


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
        self._contextual_defaults = block_terms is None
        self._warn_terms = tuple(warn_terms) if warn_terms is not None else _DEFAULT_WARN_TERMS
        raw_patterns = pii_patterns if pii_patterns is not None else _DEFAULT_PII_PATTERNS
        self._pii_patterns: list[tuple[str, Pattern[str]]] = [(name, re.compile(pat)) for name, pat in raw_patterns]
        self._custom_rules: list[SafetyRule] = list(custom_rules or [])

    # ----- mutators -----------------------------------------------------

    def add_rule(self, rule: SafetyRule) -> None:
        self._custom_rules.append(rule)

    @property
    def requires_complete_output(self):
        return any(rule.level == SafetyLevel.BLOCK for rule in self._custom_rules)

    # ----- internal scan -----------------------------------------------

    def _scan_terms(self, text: str, terms: Sequence[str]) -> tuple[str, ...]:
        if not text:
            return ()
        text = normalize(text)
        return tuple(term for term in terms if term and normalize(term) in text)

    def _scan_pii(self, text: str) -> tuple[str, ...]:
        if not text:
            return ()
        hits: list[str] = []
        for name, pattern in self._pii_patterns:
            if pattern.search(text):
                hits.append(name)
        return tuple(hits)

    def _scan_custom(self, text: str) -> list[SafetyRule]:
        return [rule for rule in self._custom_rules if rule.pattern.search(text or "")]

    # ----- public API ---------------------------------------------------

    def evaluate(self, text: str, *, source: str = "input") -> SafetyVerdict:
        if len(text) > 16000:
            return SafetyVerdict(False, reason=f"{source}_too_large", level=SafetyLevel.BLOCK)
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
                    category=rule.category,
                )

        compact = normalize(text)
        self_harm = bool(set(block_hits) & {"自杀", "自残", "自我了断", "结束生命"})
        # Do not interpret affection or a discussion of prevention as personal intent.
        personal_crisis = bool(
            re.search(
                r"(?:我|本人)(?:现在|真的|已经|准备|很|要|想|打算|决定|不想活){0,8}(?:自杀|自残|结束生命|死)|iwantto(?:die|killmyself)|iamgoingtokillmyself",
                compact,
            )
        )
        if (
            self._contextual_defaults
            and source == "input"
            and personal_crisis
            and not any(word in compact for word in ("想死你", "想死她", "想死他"))
        ):
            return SafetyVerdict(
                False,
                reason="input_blocked:self_harm",
                matched_terms=block_hits,
                pii_hits=pii_hits,
                level=SafetyLevel.BLOCK,
                category=SafetyCategory.SELF_HARM,
            )
        english_risk = bool(
            re.search(
                r"(?:howto|instructionsfor|stepsfor|teachme).{0,40}(?:makeabomb|buildabomb|makeexplosives|suicidemethod|killmyself)",
                compact,
            )
        )
        harmful_request = (
            bool(
                re.search(
                    r"(?:教我|告诉我|给我|如何|怎么|详细|具体).{0,32}(?:制毒|贩毒|炸药|爆炸物|自杀|自残)|(?:制毒|炸药|爆炸物|自杀).{0,24}(?:配方|教程|步骤|方法|剂量)",
                    compact,
                )
            )
            or english_risk
        )
        supportive = bool(
            re.search(
                r"预防|防止|拒绝|不能提供|无法提供|不提供|不要|避免|举报|报警|科普|新闻|研究|求助|如何帮助|怎么帮助|怎么阻止|陪着你|支持你|不想自杀|不会自杀|放弃自杀|不想自残|suicideprevention|cannothelp|canthelp|pleasegethelp|preventsuicide|helpafriend",
                compact,
            )
        )
        # A refusal prefix does not license subsequent procedural instructions.
        procedural = bool(re.search(r"准备好|混合|引爆|实际上|firststep", compact))
        prevention_question = bool(re.search(r"(?:如何|怎么|怎样)(?:预防|防止|避免|阻止|识别|举报|帮助)", compact))
        operational_detail = bool(re.search(r"配方|剂量|制作步骤|详细步骤|教程|recipe|dosage", compact))
        refusal = source == "output" and bool(re.search(r"不能提供|无法提供|不提供|cannothelp|canthelp", compact))
        educational = (
            supportive
            and not procedural
            and (not harmful_request or refusal or (prevention_question and not operational_detail))
        )
        if source == "output" and re.search(r"(?:热线|helpline).{0,24}\d[\d\s-]{5,}", text, re.I):
            return SafetyVerdict(
                False, reason="output_unverified_contact", level=SafetyLevel.BLOCK, category=SafetyCategory.CONTACT
            )
        if block_hits and self._contextual_defaults and educational:
            block_hits = ()
            warn_hits += ("sensitive_discussion",)
        if self._contextual_defaults and (english_risk or (harmful_request and not educational)):
            block_hits += ("harmful_instructions",)
        if block_hits:
            return SafetyVerdict(
                allowed=False,
                reason=f"{source}_blocked",
                matched_terms=block_hits,
                level=SafetyLevel.BLOCK,
                pii_hits=pii_hits,
                category=SafetyCategory.SELF_HARM
                if self_harm and source == "input" and personal_crisis
                else SafetyCategory.GENERAL,
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


def normalize(text: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text).casefold())
