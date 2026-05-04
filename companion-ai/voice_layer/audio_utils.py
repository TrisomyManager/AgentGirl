"""Audio processing utilities — format conversion, duration detection, temp storage."""

import io
import os
import uuid
from pathlib import Path
from typing import BinaryIO, Union

from pydub import AudioSegment

from shared.config import get_settings


# ---------------------------------------------------------------------------
# Temp storage
# ---------------------------------------------------------------------------

def _get_temp_dir() -> Path:
    settings = get_settings()
    temp_dir = Path(os.environ.get("COMPANION_VOICE_TEMP_DIR", "/tmp/companion_voice"))
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


# ---------------------------------------------------------------------------
# Duration detection
# ---------------------------------------------------------------------------

async def get_audio_duration(audio_data: Union[bytes, BinaryIO, str, Path], fmt: str | None = None) -> float:
    """Return audio duration in seconds.

    Supports file path, bytes, or file-like object.
    Format is auto-detected from extension or content when *fmt* is None.
    """
    if isinstance(audio_data, (str, Path)):
        path = Path(audio_data)
        fmt = fmt or path.suffix.lstrip(".").lower()
        audio = AudioSegment.from_file(str(path), format=fmt or None)
    elif isinstance(audio_data, bytes):
        fmt = fmt or "mp3"
        audio = AudioSegment.from_file(io.BytesIO(audio_data), format=fmt)
    else:
        fmt = fmt or "mp3"
        audio = AudioSegment.from_file(audio_data, format=fmt)

    return audio.duration_seconds


# ---------------------------------------------------------------------------
# Format conversion
# ---------------------------------------------------------------------------

async def convert_audio_format(
    audio_data: bytes,
    source_fmt: str,
    target_fmt: str = "mp3",
    target_sample_rate: int | None = None,
    target_channels: int | None = None,
) -> bytes:
    """Convert audio to target format/sample-rate/channels."""
    audio = AudioSegment.from_file(io.BytesIO(audio_data), format=source_fmt)

    if target_sample_rate:
        audio = audio.set_frame_rate(target_sample_rate)
    if target_channels:
        audio = audio.set_channels(target_channels)

    buf = io.BytesIO()
    audio.export(buf, format=target_fmt)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Temp storage helpers
# ---------------------------------------------------------------------------

async def save_temp_audio(audio_data: bytes, fmt: str = "mp3") -> str:
    """Save audio bytes to temp dir and return local file path."""
    temp_dir = _get_temp_dir()
    filename = f"{uuid.uuid4().hex}.{fmt}"
    filepath = temp_dir / filename
    filepath.write_bytes(audio_data)
    return str(filepath)


async def cleanup_temp_audio(filepath: str) -> None:
    """Remove a temp audio file if it exists."""
    path = Path(filepath)
    if path.exists():
        path.unlink()
