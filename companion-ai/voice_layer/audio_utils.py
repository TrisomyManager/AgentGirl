"""Audio processing utilities — format conversion, duration detection, temp storage."""

import io
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import BinaryIO

from pydub import AudioSegment

# ---------------------------------------------------------------------------
# ffmpeg / ffprobe discovery — works on both dev and packaged C-end builds.
# Search order:
#   1. COMPANION_FFMPEG_DIR env var
#   2. <repo>/companion-ai/.bin/ (vendored portable ffmpeg)
#   3. <executable>/ffmpeg/ (PyInstaller-style bundle)
#   4. PATH (system-installed)
# Whichever wins gets bound to pydub so users never need to install anything.
# ---------------------------------------------------------------------------


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    env_dir = os.environ.get("COMPANION_FFMPEG_DIR")
    if env_dir:
        dirs.append(Path(env_dir))
    here = Path(__file__).resolve()
    dirs.append(here.parent.parent / ".bin")
    dirs.append(Path(sys.executable).resolve().parent / "ffmpeg")
    return dirs


def _find_binary(name: str) -> str | None:
    exe = f"{name}.exe" if os.name == "nt" else name
    for d in _candidate_dirs():
        candidate = d / exe
        if candidate.exists():
            return str(candidate)
    return shutil.which(name)


def _configure_pydub() -> None:
    ffmpeg_path = _find_binary("ffmpeg")
    ffprobe_path = _find_binary("ffprobe")
    if ffmpeg_path:
        AudioSegment.converter = ffmpeg_path
    if ffprobe_path:
        AudioSegment.ffprobe = ffprobe_path
        # pydub also reads PATH for ffprobe in some code paths — make sure
        # the parent dir is searchable too.
        os.environ["PATH"] = os.path.dirname(ffprobe_path) + os.pathsep + os.environ.get("PATH", "")


_configure_pydub()


# ---------------------------------------------------------------------------
# Temp storage
# ---------------------------------------------------------------------------

def get_voice_temp_directory() -> Path:
    """Directory for temporary synthesized audio files (served as ``/static/voice/…``)."""
    import tempfile

    default_dir = Path(tempfile.gettempdir()) / "companion_voice"
    temp_dir = Path(os.environ.get("COMPANION_VOICE_TEMP_DIR", default_dir))
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


# ---------------------------------------------------------------------------
# Duration detection
# ---------------------------------------------------------------------------

async def get_audio_duration(audio_data: bytes | BinaryIO | str | Path, fmt: str | None = None) -> float:
    """Return audio duration in seconds.

    Supports file path, bytes, or file-like object.
    Format is auto-detected from extension or content when *fmt* is None.
    Falls back to a rough MP3 bitrate-based estimate if ffmpeg/ffprobe is
    missing on the host (common on Windows dev boxes).
    """
    try:
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
    except Exception:  # noqa: BLE001 - ffmpeg/ffprobe missing or decode failure
        if isinstance(audio_data, bytes):
            byte_len = len(audio_data)
        elif isinstance(audio_data, (str, Path)):
            try:
                byte_len = Path(audio_data).stat().st_size
            except OSError:
                return 0.0
        else:
            return 0.0
        # Assume ~128 kbps MP3 → 16 KB/s.
        return max(0.0, byte_len / 16000.0)


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
    temp_dir = get_voice_temp_directory()
    filename = f"{uuid.uuid4().hex}.{fmt}"
    filepath = temp_dir / filename
    filepath.write_bytes(audio_data)
    return str(filepath)


async def cleanup_temp_audio(filepath: str) -> None:
    """Remove a temp audio file if it exists."""
    path = Path(filepath)
    if path.exists():
        path.unlink()
