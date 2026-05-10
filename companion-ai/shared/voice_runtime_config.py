"""[Deprecated] ``shared.voice_runtime_config`` 已物理搬迁至 ``shared_runtime.voice_runtime_config``.

P1-E (V2.1) 起, 本文件仅做 re-export shim.
新代码请使用 ``from shared_runtime import get_runtime_voice_config, update_runtime_voice_config``.
"""

from __future__ import annotations

from shared_runtime.voice_runtime_config import (  # noqa: F401
    clear_runtime_voice_config,
    get_runtime_voice_config,
    load_voice_config_from_disk,
    save_voice_config_to_disk,
    update_runtime_voice_config,
    voice_config_file_path,
)

__all__ = [
    "clear_runtime_voice_config",
    "get_runtime_voice_config",
    "update_runtime_voice_config",
    "save_voice_config_to_disk",
    "load_voice_config_from_disk",
    "voice_config_file_path",
]
