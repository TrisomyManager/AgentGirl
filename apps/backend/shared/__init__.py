"""Companion AI — Shared contracts and utilities.

注: P1-C 起, ``shared.models`` / ``shared.events`` 已变为面向 ``shared_contracts``
的 deprecated re-export shim. 这里仍使用 ``from .models import *`` 以拿到完整
符号集 (包括新增的 Platform/RelationshipMetrics/ActionType/…).
"""

from __future__ import annotations

from .models import *  # noqa: F401,F403
from .models import __all__ as _models_all
from .events import *  # noqa: F401,F403
from .events import __all__ as _events_all
from .config import Settings, get_settings

__all__ = [
    *list(_models_all),
    *list(_events_all),
    "Settings",
    "get_settings",
]
