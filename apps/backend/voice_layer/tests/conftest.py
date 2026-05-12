"""Isolate voice disk config and realtime registry for voice_layer tests."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Point voice JSON at an empty temp file so dev machines' real config never leaks."""
    if os.environ.get("COMPANION_VOICE_DISABLE_TEST_ISOLATION", "").lower() in ("1", "true", "yes", "on"):
        return
    td = tempfile.mkdtemp(prefix="companion_voice_cfg_")
    p = Path(td) / "voice_cfg.json"
    p.write_text(json.dumps({}), encoding="utf-8")
    os.environ["COMPANION_VOICE_CONFIG_PATH"] = str(p)


@pytest.fixture(autouse=True)
def _reset_voice_runtime_state() -> None:
    from shared_runtime.voice_runtime_config import clear_runtime_voice_config
    from voice_layer.providers.realtime import reset_realtime_registry

    clear_runtime_voice_config()
    reset_realtime_registry()
    yield
    clear_runtime_voice_config()
    reset_realtime_registry()
