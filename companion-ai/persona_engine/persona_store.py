"""Load and cache the structured persona from YAML.

The companion has a single soul file (`data/soul.yaml`) that defines her
static profile.  This module reads it once at startup and exposes a
`PersonaProfile` Pydantic model for the rest of the service.
"""

from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import structlog
import yaml

# Allow running inside the package as well as from repo root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SOUL_PATH = _PROJECT_ROOT / "persona_engine" / "data" / "soul.yaml"

logger = structlog.get_logger("persona_engine.persona_store")


class PersonaStoreError(Exception):
    """Raised when the soul file is missing or malformed."""


@lru_cache(maxsize=1)
def load_persona(path: str | Path | None = None) -> Dict[str, Any]:
    """Load the raw soul YAML and return it as a plain dict.

    The result is cached for the lifetime of the process so that repeated
    calls are essentially free.
    """
    target = Path(path) if path else _DEFAULT_SOUL_PATH
    if not target.exists():
        raise PersonaStoreError(f"Soul file not found: {target}")

    with target.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise PersonaStoreError("Soul file must contain a top-level mapping.")

    logger.info("persona.loaded", path=str(target), name=data.get("name"))
    return data


def _parse_emotion_baseline(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert the YAML emotional_baseline block into an EmotionState dict."""
    from shared.models import EmotionTag

    baseline = {
        "primary": EmotionTag(raw.get("primary", "calm")),
        "intensity": float(raw.get("intensity", 0.4)),
        "valence": float(raw.get("valence", 0.0)),
        "arousal": float(raw.get("arousal", 0.3)),
        "trigger": raw.get("trigger", "baseline"),
        "timestamp": datetime.utcnow(),
    }
    return baseline


def get_persona_profile(path: str | Path | None = None) -> "PersonaProfile":
    """Return a fully-hydrated `PersonaProfile` from the soul YAML."""
    from shared.models import PersonaProfile

    raw = load_persona(path)
    baseline_raw = raw.get("emotional_baseline", {})

    profile = PersonaProfile(
        persona_id="default",
        name=raw["name"],
        age_hint=raw.get("age_hint"),
        gender_hint=raw.get("gender_hint"),
        core_traits=raw.get("core_traits", []),
        communication_style=raw.get("communication_style", ""),
        values=raw.get("values", []),
        backstory=raw.get("backstory", ""),
        relationship_goals=raw.get("relationship_goals", []),
        emotional_baseline=_parse_emotion_baseline(baseline_raw),
        voice_preference=raw.get("voice_preference"),
        avatar_2d_url=raw.get("avatar_2d_url"),
    )
    return profile


async def get_persona_profile_async(path: str | Path | None = None) -> "PersonaProfile":
    """Async wrapper around `get_persona_profile` for use in FastAPI handlers."""
    # YAML parsing is fast enough that we can call the sync version directly.
    # If the file were remote, we'd add an async HTTP client here.
    return get_persona_profile(path)
