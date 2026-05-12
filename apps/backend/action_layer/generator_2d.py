"""[Deprecated] re-export shim. See ``action_layer/__init__.py`` for migration plan."""

from __future__ import annotations

from action_executor.action2d.generator_2d import (  # noqa: F401
    Action2DGenerator,
)

__all__ = ["Action2DGenerator"]
