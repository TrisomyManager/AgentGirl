"""[Deprecated] re-export shim. See ``action_layer/__init__.py`` for migration plan."""

from __future__ import annotations

from action_executor.action2d.api import (  # noqa: F401
    ActionGenerateRequest,
    LipSyncRequest,
    generate_action,
    generate_lip_sync,
    list_templates,
    router,
)

__all__ = [
    "router",
    "ActionGenerateRequest",
    "LipSyncRequest",
    "generate_action",
    "generate_lip_sync",
    "list_templates",
]
