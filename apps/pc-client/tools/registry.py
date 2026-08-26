"""Local tool registry — aligned with backend action_executor.registry pattern."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


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
        return [t.to_meta() for t in self._tools.values()]

    def exec(self, name: str, params: Dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(ok=False, message=f"Unknown tool: {name}")
        try:
            return tool.handler(params)
        except Exception as exc:
            return ToolResult(ok=False, message=str(exc))


_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
