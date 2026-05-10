"""Runtime voice configuration with disk persistence (P1-E 物理搬迁完成 / V2.1).

Mirrors the pattern in ``shared_runtime/llm_client.py`` so users can update
ASR/TTS provider, API key, base URL, model and voice ID at runtime via the
frontend.

Default file location is the per-user config directory (not the git repo) so
API keys are not accidentally committed. Override with ``COMPANION_VOICE_CONFIG_PATH``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger("shared_runtime.voice_runtime_config")

_runtime_voice_config: dict[str, Any] = {}


def _default_voice_config_path() -> Path:
    """Per-user path: avoid writing secrets into the repository checkout."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "companion-ai" / "companion_voice_config.json"
        return Path.home() / "companion-ai" / "companion_voice_config.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "companion-ai" / "companion_voice_config.json"
    return Path.home() / ".config" / "companion-ai" / "companion_voice_config.json"


def voice_config_file_path() -> Path:
    """Resolved path to the on-disk voice JSON (respects COMPANION_VOICE_CONFIG_PATH)."""
    explicit = os.environ.get("COMPANION_VOICE_CONFIG_PATH")
    if explicit:
        return Path(explicit)
    return _default_voice_config_path()


def update_runtime_voice_config(**kwargs: Any) -> None:
    """Merge kwargs into runtime voice config (empty string clears a key)."""
    for k, v in kwargs.items():
        if v == "":
            _runtime_voice_config.pop(k, None)
        else:
            _runtime_voice_config[k] = v


def get_runtime_voice_config() -> dict[str, Any]:
    return dict(_runtime_voice_config)


def clear_runtime_voice_config() -> None:
    """Clear in-memory voice config (used by tests). Does not delete the file."""
    _runtime_voice_config.clear()


def save_voice_config_to_disk() -> None:
    path = voice_config_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_runtime_voice_config, indent=2), encoding="utf-8")
        logger.info("voice_config.saved", path=str(path))
    except Exception as exc:
        logger.warning("voice_config.save_failed", path=str(path), error=str(exc))


def load_voice_config_from_disk() -> None:
    path = voice_config_file_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _runtime_voice_config.update(data)
            logger.info(
                "voice_config.loaded_from_disk",
                path=str(path),
                key_count=len(data),
            )
    except Exception as exc:
        logger.warning("voice_config.load_failed", path=str(path), error=str(exc))


__all__ = [
    "clear_runtime_voice_config",
    "get_runtime_voice_config",
    "load_voice_config_from_disk",
    "save_voice_config_to_disk",
    "update_runtime_voice_config",
    "voice_config_file_path",
]
