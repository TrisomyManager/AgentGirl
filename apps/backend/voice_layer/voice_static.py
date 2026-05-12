"""Serve synthesized MP3 files under ``/static/voice``."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import voice_layer.audio_utils as _audio_utils


def mount_voice_static_files(app: FastAPI) -> None:
    """Mount the TTS temp directory so ``/static/voice/<file>.mp3`` returns audio."""
    directory = _audio_utils.get_voice_temp_directory()
    directory.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/static/voice",
        StaticFiles(directory=str(directory)),
        name="companion_voice_audio",
    )
