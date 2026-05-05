"""Project-root pytest config.

Sets COMPANION_LITE_MODE before any test imports so memory_system / shared.database
modules pick up SQLite-friendly branches at import time. Also clears the
@lru_cache on get_settings() in case anything was imported earlier.
"""

import os

os.environ.setdefault("COMPANION_LITE_MODE", "true")

from shared.config import get_settings  # noqa: E402

get_settings.cache_clear()

# Defensive: if memory_system.* or shared.database were already imported
# (e.g. via plugin auto-import), refresh their module-level `settings` ref.
import importlib  # noqa: E402
import sys  # noqa: E402

for _mod_name in ("memory_system.db", "memory_system.vector_store", "shared.database"):
    _mod = sys.modules.get(_mod_name)
    if _mod is not None and hasattr(_mod, "settings"):
        _mod.settings = get_settings()
