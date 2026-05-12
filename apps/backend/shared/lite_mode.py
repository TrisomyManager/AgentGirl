"""DEPRECATED shim —— Lite Mode 物理实现已搬迁到 ``shared_runtime.lite_mode``.

P1-D (V2.1) 起, 本文件保留作为反向 re-export 入口, 以兼容老代码:
    from shared.lite_mode import InMemoryEventBus  # 仍能跑

新代码应改用:
    from shared_runtime import InMemoryEventBus, InMemoryShortTermMemory

后续波次完全清理调用方后, 本 shim 可删除.
"""

from __future__ import annotations

from shared_runtime.lite_mode import (
    EventHandler,
    InMemoryEventBus,
    InMemoryShortTermMemory,
)

__all__ = ["EventHandler", "InMemoryEventBus", "InMemoryShortTermMemory"]
