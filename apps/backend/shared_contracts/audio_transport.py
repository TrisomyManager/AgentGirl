"""Versioned audio payload frames. Control metadata remains bounded JSON."""

import struct
from dataclasses import dataclass

PROTOCOL = "framed-v1"
MAX_AUDIO_BYTES = 2 * 1024 * 1024
HEADER = struct.Struct(">4sBBHIII")


class AudioFrameError(ValueError):
    pass


@dataclass(frozen=True)
class AudioFrame:
    stream_id: int
    sequence: int
    payload: bytes


def encode_audio_frame(payload: bytes, *, stream_id: int, sequence: int) -> bytes:
    if not payload or len(payload) > MAX_AUDIO_BYTES:
        raise AudioFrameError("Invalid audio payload size")
    if any(type(value) is not int or not 0 <= value <= 0xFFFFFFFF for value in (stream_id, sequence)):
        raise AudioFrameError("Invalid audio frame counter")
    return HEADER.pack(b"CNAV", 1, 1, 0, stream_id, sequence, len(payload)) + payload


def decode_audio_frame(data: bytes) -> AudioFrame:
    if not HEADER.size < len(data) <= HEADER.size + MAX_AUDIO_BYTES:
        raise AudioFrameError("Invalid audio frame size")
    magic, version, kind, reserved, stream_id, sequence, size = HEADER.unpack_from(data)
    if (magic, version, kind, reserved) != (b"CNAV", 1, 1, 0) or size != len(data) - HEADER.size:
        raise AudioFrameError("Invalid audio frame header")
    return AudioFrame(stream_id, sequence, data[HEADER.size :])
