"""Pluggable action registry.

Handlers are async callables that take a ``params`` dict and return an
``ActionResult``. They register themselves into the process-wide
``ActionRegistry`` either explicitly via ``register_action`` (used by
``BUILTIN_ACTIONS``) or via the ``@register_action(...)`` decorator.

The registry is intentionally simple — no DI, no per-user namespaces —
because it's the first thing the orchestrator hits when intent_router
returns ``TOOL_USE`` / ``ACTION_REQUEST``. We can layer scopes on later.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger("action_executor.registry")


@dataclass
class ActionResult:
    """Uniform return shape from every action handler.

    - ``ok``: did the handler complete? False = surface error to user.
    - ``message``: human-readable assistant reply (rendered into the
      chat bubble in lieu of a fresh LLM call).
    - ``data``: structured payload — e.g. for ``set_reminder`` this
      contains the freshly created reminder id and fire-at timestamp.
    - ``proactive_push``: optional event payload that should be pushed
      to all currently-connected clients later (used when an action
      triggers asynchronously, e.g. a reminder that fires N seconds
      from now). Empty for synchronous-only actions like ``get_time``.
    """

    ok: bool = True
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    proactive_push: Optional[Dict[str, Any]] = None


HandlerFn = Callable[[Dict[str, Any]], Awaitable[ActionResult]]


@dataclass
class ActionDefinition:
    """One registered handler, with metadata for /actions/list."""

    name: str
    description: str
    params_schema: Dict[str, Any]
    keywords: List[str]
    handler: HandlerFn

    def to_meta(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "params_schema": self.params_schema,
            "keywords": list(self.keywords),
        }


class ActionRegistry:
    """Process-wide registry of action handlers."""

    def __init__(self) -> None:
        self._actions: Dict[str, ActionDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        params_schema: Optional[Dict[str, Any]] = None,
        keywords: Optional[List[str]] = None,
    ) -> Callable[[HandlerFn], HandlerFn]:
        def _decorator(fn: HandlerFn) -> HandlerFn:
            if not inspect.iscoroutinefunction(fn):
                raise TypeError(
                    f"Action handler {name!r} must be an async function (got {type(fn).__name__})"
                )
            if name in self._actions:
                logger.info("action.replaced", name=name)
            self._actions[name] = ActionDefinition(
                name=name,
                description=description,
                params_schema=params_schema or {},
                keywords=list(keywords or []),
                handler=fn,
            )
            logger.info("action.registered", name=name)
            return fn

        return _decorator

    def has(self, name: str) -> bool:
        return name in self._actions

    def list_actions(self) -> List[Dict[str, Any]]:
        return [d.to_meta() for d in self._actions.values()]

    def find_by_keyword(self, text: str) -> Optional[str]:
        """Cheap keyword match for routing user messages without an LLM.

        Returns the first action whose keyword list shows up in ``text``
        (case-insensitive), or ``None``. The order of registration is the
        priority order — register more specific handlers first.
        """
        if not text:
            return None
        lowered = text.lower()
        for action in self._actions.values():
            for keyword in action.keywords:
                if keyword.lower() in lowered:
                    return action.name
        return None

    async def dispatch(self, name: str, params: Dict[str, Any]) -> ActionResult:
        """Execute a registered action and surface a uniform error if missing."""
        action = self._actions.get(name)
        if action is None:
            logger.warning("action.unknown", name=name)
            return ActionResult(
                ok=False,
                message=f"我还不会处理这种请求（未注册的动作：{name}）。",
                data={"error": "unknown_action", "name": name},
            )
        try:
            result = await action.handler(params or {})
            if result is None:  # be lenient — handlers might forget to return
                result = ActionResult(ok=True, message="")
            logger.info("action.executed", name=name, ok=result.ok)
            return result
        except Exception as exc:
            logger.exception("action.failed", name=name, error=str(exc))
            return ActionResult(
                ok=False,
                message=f"处理 {name} 时遇到了问题：{exc}",
                data={"error": "handler_exception", "exception": str(exc)},
            )


_registry: Optional[ActionRegistry] = None


def get_registry() -> ActionRegistry:
    global _registry
    if _registry is None:
        _registry = ActionRegistry()
    return _registry


def register_action(
    name: str,
    description: str,
    params_schema: Optional[Dict[str, Any]] = None,
    keywords: Optional[List[str]] = None,
) -> Callable[[HandlerFn], HandlerFn]:
    """Decorator: register a handler on the process-wide registry."""
    return get_registry().register(
        name=name,
        description=description,
        params_schema=params_schema,
        keywords=keywords,
    )
