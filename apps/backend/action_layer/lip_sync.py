"""[Deprecated] re-export shim. See ``action_layer/__init__.py`` for migration plan."""

from __future__ import annotations

from action_executor.action2d.lip_sync import (  # noqa: F401
    LipSyncGenerator,
    Viseme,
)

__all__ = ["LipSyncGenerator", "Viseme"]
