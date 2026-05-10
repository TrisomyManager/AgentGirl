"""DEPRECATED shim —— 配置物理实现已搬迁到 ``shared_runtime.config``.

P1-D (V2.1) 起, 本文件保留作为反向 re-export 入口, 以兼容老代码:
    from shared.config import get_settings  # 仍能跑

新代码应改用:
    from shared_runtime import get_settings

后续波次完全清理调用方后, 本 shim 可删除.
"""

from __future__ import annotations

from shared_runtime.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
