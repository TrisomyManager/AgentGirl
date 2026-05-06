"""Runtime voice configuration with disk persistence.

Mirrors the pattern in ``shared/llm_client.py`` so users can update ASR/TTS
provider, API key, base URL, model and voice ID at runtime via the frontend.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import structlog

logger = structlog.get_logger("shared.voice_runtime_config")

_COMPANION_ROOT = Path(__file__).resolve().parent.parent
_runtime_voice_config: Dict[str, Any] = {}
_CONFIG_FILE = Path(
    os.getenv("COMPANION_VOICE_CONFIG_PATH", str(_COMPANION_ROOT / "companion_voice_config.json"))
)


def update_runtime_voice_config(**kwargs: Any) -> None:
    """Merge kwargs into runtime voice config (empty string clears a key)."""
    for k, v in kwargs.items():
        if v == "":
            _runtime_voice_config.pop(k, None)
        else:
            _runtime_voice_config[k] = v


def get_runtime_voice_config() -> Dict[str, Any]:
    return dict(_runtime_voice_config)


def save_voice_config_to_disk() -> None:
    try:
        _CONFIG_FILE.write_text(json.dumps(_runtime_voice_config, indent=2), encoding="utf-8")
        logger.info("voice_config.saved", path=str(_CONFIG_FILE))
    except Exception as exc:
        logger.warning("voice_config.save_failed", path=str(_CONFIG_FILE), error=str(exc))


def load_voice_config_from_disk() -> None:
    if not _CONFIG_FILE.exists():
        return
    try:
        data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _runtime_voice_config.update(data)
            logger.info("voice_config.loaded_from_disk", path=str(_CONFIG_FILE), keys=list(data.keys()))
    except Exception as exc:
        logger.warning("voice_config.load_failed", path=str(_CONFIG_FILE), error=str(exc))
