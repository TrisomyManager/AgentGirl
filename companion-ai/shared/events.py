"""DEPRECATED shim —— 事件类型物理实现已搬迁到 ``shared_contracts.events``.

P1-C (V2.1) 起, 本文件保留作为反向 re-export 入口, 以兼容老代码:
    from shared.events import TurnStartEvent  # 仍能跑

新代码应改用:
    from shared_contracts import TurnStartEvent

后续波次完全清理调用方后, 本 shim 可删除.
"""

from __future__ import annotations

from shared_contracts.events import *  # noqa: F401,F403
from shared_contracts.events import __all__ as _contracts_all

__all__ = list(_contracts_all)
