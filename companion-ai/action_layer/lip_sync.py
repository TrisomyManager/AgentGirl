"""Lip sync generator.

Input: TTS audio duration + text content
Output: lip shape keyframes (A, E, I, O, U, M, rest) with timestamps

Simple rule-based: map phonemes to lip shapes (visemes).
"""

import re
import uuid
from typing import Any

import structlog

from shared.models import ActionFrame, ActionType, EmotionTag

logger = structlog.get_logger("action_layer.lip_sync")

# ---------------------------------------------------------------------------
# Phoneme → viseme (lip shape) mapping
# ---------------------------------------------------------------------------

# Simplified Chinese pinyin + English phoneme mapping
_PHONEME_TO_VISeme: dict[str, str] = {
    # Vowels — open mouth shapes
    "a": "A", "aa": "A", "ah": "A", "ao": "A",
    "o": "O", "oo": "O", "oh": "O", "ou": "O",
    "e": "E", "ee": "E", "eh": "E", "ei": "E", "ai": "E",
    "i": "I", "ii": "I", "ih": "I", "yi": "I",
    "u": "U", "uu": "U", "uh": "U", "wu": "U", "ü": "U", "v": "U",
    # Consonants — lip shapes
    "b": "M", "p": "M", "m": "M",
    "f": "M",  # slight variation, grouped with M for MVP
    "w": "U",
}

# Regex-based mapping for multi-character phonemes (longest match first)
_VISEME_PATTERNS = [
    (re.compile(r"\b(ao|ou|ai|ei|ie|üe|an|en|in|un|ün|ang|eng|ing|ong)\b"), None),  # handled by first char
]

# Direct character-based mapping for Chinese (simplified)
_CHAR_TO_VISEME: dict[str, str] = {
    # Fallback: map common pinyin finals by their vowel
}

# English phoneme groups
_ENGLISH_VOWELS = {"a", "e", "i", "o", "u"}
_ENGLISH_CONSONANTS_M = {"b", "p", "m"}
_ENGLISH_CONSONANTS_U = {"w", "q"}


# ---------------------------------------------------------------------------
# Viseme definitions
# ---------------------------------------------------------------------------

class Viseme:
    """Lip shape constants."""

    REST = "rest"
    A = "A"    # Wide open
    E = "E"    # Mid open, spread
    I = "I"    # Slight smile, teeth visible
    O = "O"    # Rounded
    U = "U"    # Puckered
    M = "M"    # Closed lips


# ---------------------------------------------------------------------------
# Lip Sync Generator
# ---------------------------------------------------------------------------

class LipSyncGenerator:
    """Generate lip sync keyframes from text and audio duration.

    Uses a simple rule-based phoneme-to-viseme mapping.
    Total duration is matched to the TTS audio duration.
    """

    # Average speech rate: ~4-5 characters per second for Chinese
    # ~12-15 phonemes per second for English
    DEFAULT_CHARS_PER_SECOND = 4.5
    DEFAULT_PHONEMES_PER_SECOND = 12.0

    @staticmethod
    def generate(
        text: str,
        duration_ms: int,
        fps: int = 12,
    ) -> list[dict[str, Any]]:
        """Generate lip shape keyframes.

        Returns a list of {"timestamp_ms": int, "viseme": str}.
        """
        logger.info("lip_sync.generate", text_len=len(text), duration_ms=duration_ms, fps=fps)

        if not text or duration_ms <= 0:
            return [{"timestamp_ms": 0, "viseme": Viseme.REST}]

        # Extract viseme sequence from text
        visemes = LipSyncGenerator._text_to_visemes(text)

        if not visemes:
            return [{"timestamp_ms": 0, "viseme": Viseme.REST}]

        # Distribute visemes evenly across duration
        frame_interval_ms = 1000 / fps
        total_frames = max(1, int(duration_ms / frame_interval_ms))

        keyframes: list[dict[str, Any]] = []
        viseme_index = 0
        visemes_per_frame = max(1, len(visemes) / total_frames)

        for frame_idx in range(total_frames):
            timestamp_ms = int(frame_idx * frame_interval_ms)
            viseme_idx = min(int(frame_idx * visemes_per_frame), len(visemes) - 1)
            viseme = visemes[viseme_idx]

            # Hold viseme for a few frames, then transition
            keyframes.append({
                "timestamp_ms": timestamp_ms,
                "viseme": viseme,
            })

        # Ensure final rest frame at end
        if not keyframes or keyframes[-1]["timestamp_ms"] < duration_ms:
            keyframes.append({"timestamp_ms": duration_ms, "viseme": Viseme.REST})

        logger.info("lip_sync.done", keyframe_count=len(keyframes))
        return keyframes

    @staticmethod
    def _text_to_visemes(text: str) -> list[str]:
        """Convert text to a sequence of visemes."""
        visemes: list[str] = []
        text = text.lower().strip()

        # Simple approach: iterate characters and map
        i = 0
        while i < len(text):
            ch = text[i]

            # Skip whitespace and punctuation
            if ch.isspace() or ch in "，。！？、；：" ",.!?;:'\"-":
                i += 1
                continue

            # Single character mapping (no multi-char greedy matching to avoid swallowing individual vowels)
            if ch in _PHONEME_TO_VISeme:
                visemes.append(_PHONEME_TO_VISeme[ch])
            elif ch in _ENGLISH_VOWELS:
                visemes.append(ch.upper())
            elif ch in _ENGLISH_CONSONANTS_M:
                visemes.append(Viseme.M)
            elif ch in _ENGLISH_CONSONANTS_U:
                visemes.append(Viseme.U)
            else:
                # Default to rest for unmapped characters
                visemes.append(Viseme.REST)

            i += 1

        # Collapse consecutive identical visemes (with count)
        collapsed: list[str] = []
        for v in visemes:
            if not collapsed or collapsed[-1] != v:
                collapsed.append(v)

        return collapsed if collapsed else [Viseme.REST]

    @staticmethod
    def merge_with_frames(
        body_frames: list[dict[str, Any]],
        lip_keyframes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge lip sync keyframes into body animation frames.

        For each body frame, find the closest lip keyframe and attach it.
        """
        merged = []
        for body_frame in body_frames:
            ts = body_frame.get("timestamp_ms", 0)
            # Find closest lip keyframe
            closest = min(lip_keyframes, key=lambda k: abs(k["timestamp_ms"] - ts))
            merged.append({
                **body_frame,
                "lip_shape": closest["viseme"],
            })
        return merged
