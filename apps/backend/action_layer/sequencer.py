"""[Deprecated] re-export shim. See ``action_layer/__init__.py`` for migration plan."""

from __future__ import annotations

from action_executor.action2d.sequencer import ActionSequencer  # noqa: F401

__all__ = ["ActionSequencer"]
