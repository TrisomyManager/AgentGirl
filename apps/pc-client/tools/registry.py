"""Local tool registry — aligned with backend action_executor.registry pattern."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from policy import CONFIRMATION_REQUIRED, get_policy


@dataclass
class ToolResult:
    ok: bool = True
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


HandlerFn = Callable[[Dict[str, Any]], ToolResult]


@dataclass
class ToolDefinition:
    name: str
    description: str
    keywords: List[str]
    handler: HandlerFn
    risk: str = "low"
    requires_confirm: bool = False

    def to_meta(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "keywords": list(self.keywords),
            "risk": self.risk,
            "requires_confirm": self.requires_confirm,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        keywords: Optional[List[str]] = None,
        risk: str = "low",
        requires_confirm: bool = False,
    ) -> Callable[[HandlerFn], HandlerFn]:
        def _decorator(fn: HandlerFn) -> HandlerFn:
            self._tools[name] = ToolDefinition(
                name=name,
                description=description,
                keywords=keywords or [],
                handler=fn,
                risk=risk,
                requires_confirm=requires_confirm,
            )
            return fn

        return _decorator

    def list_tools(self) -> List[Dict[str, Any]]:
        policy = get_policy()
        return [
            {**t.to_meta(), "requires_confirm": t.name in CONFIRMATION_REQUIRED}
            for t in self._tools.values()
            if t.name in policy.capabilities
        ]

    def exec(self, name: str, params: Dict[str, Any], *, approved=False) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(ok=False, message="不可用的工具。")
        try:
            get_policy().authorize(name, params, approved=approved)
            return tool.handler(params)
        except (ValueError, PermissionError) as exc:
            return ToolResult(ok=False, message=str(exc))
        except Exception:
            return ToolResult(ok=False, message="本机操作未能完成。")


_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
