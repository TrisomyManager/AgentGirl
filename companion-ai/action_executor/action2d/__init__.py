"""action_executor.action2d — 2D photo-driven action generation.

P2 物理搬迁完成 (V2.1):
  - 原 ``action_layer.generator_2d``  → ``action_executor.action2d.generator_2d``
  - 原 ``action_layer.lip_sync``      → ``action_executor.action2d.lip_sync``
  - 原 ``action_layer.router``        → ``action_executor.action2d.router``
  - 原 ``action_layer.sequencer``     → ``action_executor.action2d.sequencer``
  - 原 ``action_layer.api``           → ``action_executor.action2d.api``

``action_layer/`` 仅保留 deprecated re-export shim, 计划在 V2.2 物理删除.
"""

from __future__ import annotations

from .generator_2d import Action2DGenerator
from .lip_sync import LipSyncGenerator, Viseme
from .router import ActionRouter
from .sequencer import ActionSequencer

__all__ = [
    "Action2DGenerator",
    "ActionRouter",
    "ActionSequencer",
    "LipSyncGenerator",
    "Viseme",
]
