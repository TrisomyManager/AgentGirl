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
_PERSONAS_DIR = _PROJECT_ROOT / "persona_engine" / "data" / "personas"

logger = structlog.get_logger("persona_engine.persona_store")


class PersonaStoreError(Exception):
    """Raised when the soul file is missing or malformed."""


# ---------------------------------------------------------------------------
# PersonaRegistry —— 波次 4 多角色化 (ADR-006 硬约束 3)
# 第三方宿主可通过 role_id 切换人格, 默认 role_id="default" -> data/personas/default.yaml
# 老路径 data/soul.yaml 仍作为兜底兼容
# ---------------------------------------------------------------------------


def _persona_path_for(role_id: str) -> Path:
    """Resolve the YAML path for a given role_id."""
    candidate = _PERSONAS_DIR / f"{role_id}.yaml"
    if candidate.exists():
        return candidate
    # 兼容: 旧 single-soul 部署
    if role_id == "default" and _DEFAULT_SOUL_PATH.exists():
        return _DEFAULT_SOUL_PATH
    raise PersonaStoreError(
        f"Persona yaml not found for role_id={role_id!r}: {candidate}"
    )


@lru_cache(maxsize=16)
def load_persona_by_role(role_id: str = "default") -> Dict[str, Any]:
    """Load a persona yaml by role_id (cached per role_id)."""
    return load_persona(_persona_path_for(role_id))


def list_available_personas() -> list[str]:
    """List all role_ids available under data/personas/*.yaml."""
    if not _PERSONAS_DIR.exists():
        return ["default"] if _DEFAULT_SOUL_PATH.exists() else []
    return sorted(p.stem for p in _PERSONAS_DIR.glob("*.yaml"))


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


def get_persona_profile(path: str | Path | None = None, *, role_id: str | None = None) -> "PersonaProfile":
    """Return a fully-hydrated `PersonaProfile`.

    Resolution order:
    - 显式 ``path`` (兼容老 API)
    - ``role_id`` (波次 4 多角色化, 走 PersonaRegistry)
    - 兜底: ``data/soul.yaml`` (单角色历史路径)
    """
    from shared.models import PersonaProfile

    if path is not None:
        raw = load_persona(path)
        resolved_role_id = role_id or "default"
    else:
        rid = role_id or "default"
        raw = load_persona_by_role(rid)
        resolved_role_id = rid
    baseline_raw = raw.get("emotional_baseline", {})

    profile = PersonaProfile(
        persona_id=resolved_role_id,
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


async def get_persona_profile_async(path: str | Path | None = None, *, role_id: str | None = None) -> "PersonaProfile":
    """Async wrapper around `get_persona_profile` for use in FastAPI handlers."""
    # YAML parsing is fast enough that we can call the sync version directly.
    # If the file were remote, we'd add an async HTTP client here.
    return get_persona_profile(path, role_id=role_id)
