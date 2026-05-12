"""[Deprecated] ``action_layer`` 已物理合并入 ``action_executor.action2d``.

P2 (V2.1) 起本包仅做 re-export shim:
  - ``action_layer.generator_2d`` → ``action_executor.action2d.generator_2d``
  - ``action_layer.lip_sync``     → ``action_executor.action2d.lip_sync``
  - ``action_layer.router``       → ``action_executor.action2d.router``
  - ``action_layer.sequencer``    → ``action_executor.action2d.sequencer``
  - ``action_layer.api``          → ``action_executor.action2d.api``
  - ``action_layer.main``         → ``action_executor.action2d.main``

新代码请直接 ``from action_executor.action2d import ...``.
计划在 V2.2 物理删除本目录.
"""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "action_layer 已物理迁移至 action_executor.action2d; "
    "本包仅作 deprecated re-export shim, 计划在 V2.2 物理删除. "
    "请改用 'from action_executor.action2d import ...'.",
    DeprecationWarning,
    stacklevel=2,
)

from action_executor.action2d.generator_2d import Action2DGenerator
from action_executor.action2d.lip_sync import LipSyncGenerator
from action_executor.action2d.router import ActionRouter
from action_executor.action2d.sequencer import ActionSequencer

__all__ = [
    "Action2DGenerator",
    "ActionRouter",
    "LipSyncGenerator",
    "ActionSequencer",
]
