"""onboarding —— 新用户引导与初始化流程 (P1-B 可用实现).

设计目标:
- 第一次接入的新用户走一遍"角色选择 → 称呼/语言偏好 → 初始问候"流程
- 与 persona_engine 解耦: 仅生产 OnboardingResult, 由 core_orchestrator 负责落库
- 第三方宿主可自定义流程步骤, 替换默认问答模板

P1-B 升级要点:
- 新增 ``OnboardingFlow`` 状态机: ``current_prompt() / submit_answer() / is_complete``
- 新增 ``apply_to_profile()``: 把 OnboardingResult 同步到 ``user_profile.UserProfileStore``
- 提示模板可注入, 第三方宿主可定制
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "OnboardingStep",
    "OnboardingResult",
    "OnboardingFlow",
    "default_steps",
    "apply_to_profile",
]


@dataclass(frozen=True)
class OnboardingStep:
    key: str
    prompt: str
    optional: bool = False


@dataclass
class OnboardingResult:
    user_id: str
    role_id: str = "default"
    nickname: Optional[str] = None
    locale: str = "zh-CN"
    completed_steps: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


def default_steps() -> List[OnboardingStep]:
    """默认四步引导, 第三方宿主可替换."""
    return [
        OnboardingStep("role", "想先和谁聊聊呢？(默认:陪伴者 / 也可以选择 aria)"),
        OnboardingStep("nickname", "希望我怎么称呼你呀？", optional=True),
        OnboardingStep("locale", "你更习惯中文还是英文？(zh-CN / en-US)", optional=True),
        OnboardingStep("greeting", "想聊点什么开始？心情、计划，或者只是随便说说都可以~"),
    ]


def _get_known_roles() -> set[str]:
    try:
        from persona_engine.persona_store import list_available_personas
        return set(list_available_personas())
    except Exception:
        return {"default"}


_KNOWN_LOCALES = {"zh-CN", "en-US"}


class OnboardingFlow:
    """顺序问答状态机. 每次 ``submit_answer`` 推进一步."""

    def __init__(
        self,
        user_id: str,
        steps: Optional[List[OnboardingStep]] = None,
    ) -> None:
        self.user_id = user_id
        self.steps: List[OnboardingStep] = list(steps or default_steps())
        self.result = OnboardingResult(user_id=user_id)
        self._index = 0

    # ----- query --------------------------------------------------------

    @property
    def is_complete(self) -> bool:
        return self._index >= len(self.steps)

    def current_step(self) -> Optional[OnboardingStep]:
        if self.is_complete:
            return None
        return self.steps[self._index]

    def current_prompt(self) -> Optional[str]:
        step = self.current_step()
        return step.prompt if step else None

    # ----- mutate -------------------------------------------------------

    def submit_answer(self, answer: str) -> Optional[OnboardingStep]:
        """Apply ``answer`` to current step, advance, return next step (or None)."""
        step = self.current_step()
        if step is None:
            return None
        normalized = (answer or "").strip()

        if step.key == "role":
            role = normalized.lower() or "default"
            self.result.role_id = role if role in _get_known_roles() else "default"
        elif step.key == "nickname":
            if normalized:
                self.result.nickname = normalized
        elif step.key == "locale":
            self.result.locale = normalized if normalized in _KNOWN_LOCALES else "zh-CN"
        elif step.key == "greeting":
            if normalized:
                self.result.extras["initial_greeting"] = normalized
        else:
            self.result.extras[step.key] = normalized

        self.result.completed_steps.append(step.key)
        self._index += 1
        return self.current_step()

    def skip(self) -> Optional[OnboardingStep]:
        """Skip current step (only allowed if optional)."""
        step = self.current_step()
        if step is None:
            return None
        if not step.optional:
            raise ValueError(f"step '{step.key}' is required")
        self.result.completed_steps.append(step.key)
        self._index += 1
        return self.current_step()


async def apply_to_profile(result: OnboardingResult, store: Any) -> None:
    """把 OnboardingResult 同步到 ``user_profile.UserProfileStore``.

    ``store`` 必须实现 ``upsert(snapshot)``;
    通常传入 ``user_profile.get_default_store()``.
    """
    from user_profile import UserProfileSnapshot

    snapshot = UserProfileSnapshot(
        user_id=result.user_id,
        display_name=result.nickname,
        locale=result.locale or "zh-CN",
        preferences={
            "role_id": result.role_id,
        },
        metadata={
            "onboarding_completed_steps": list(result.completed_steps),
            **({"initial_greeting": result.extras["initial_greeting"]}
               if "initial_greeting" in result.extras else {}),
        },
    )
    await store.upsert(snapshot)
