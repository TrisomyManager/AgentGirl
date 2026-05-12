"""Runtime singletons for persona_engine internal engines.

In monolithic mode, ``core_orchestrator/state_machine.py`` directly calls
``_recall_memory_monolithic`` which skips the FastAPI app lifecycle that
normally initialises ``EmotionEngine`` and ``RelationshipTracker``. This
module provides lazy singleton access so the orchestrator can read/write
persisted personality state without going through HTTP.

Hosts can inject their own implementations via ``set_emotion_engine`` /
``set_relationship_tracker``.
"""

from __future__ import annotations

from typing import Optional

import structlog

from persona_engine.emotion_engine import EmotionEngine
from persona_engine.relationship_tracker import RelationshipTracker

logger = structlog.get_logger("persona_engine.runtime")

_emotion_engine: Optional[EmotionEngine] = None
_relationship_tracker: Optional[RelationshipTracker] = None


def get_emotion_engine() -> EmotionEngine:
    """Return the process-level EmotionEngine singleton.

    In Lite / monolithic mode, this is a plain in-memory engine (no Redis).
    Call ``set_emotion_engine()`` during app startup to seed it with a
    Redis-backed instance.
    """
    global _emotion_engine
    if _emotion_engine is None:
        _emotion_engine = EmotionEngine(redis_client=None)
        logger.info("emotion_engine.created", backend="in_memory")
    return _emotion_engine


def get_relationship_tracker() -> RelationshipTracker:
    """Return the process-level RelationshipTracker singleton.

    In Lite mode, this tries to use SQLite (via ``shared.database``); falls
    back to an in-memory-only tracker when no DB is available.
    """
    global _relationship_tracker
    if _relationship_tracker is None:
        try:
            from shared.database import AsyncSessionLocal

            _relationship_tracker = RelationshipTracker(
                redis_client=None,
                db_pool=None,
                sqlite_session_factory=AsyncSessionLocal,
            )
            logger.info("relationship_tracker.created", backend="sqlite")
        except Exception:
            _relationship_tracker = RelationshipTracker(
                redis_client=None,
                db_pool=None,
                sqlite_session_factory=None,
            )
            logger.info("relationship_tracker.created", backend="in_memory")
    return _relationship_tracker


def set_emotion_engine(engine: EmotionEngine) -> None:
    """Inject a host-provided EmotionEngine."""
    global _emotion_engine
    _emotion_engine = engine


def set_relationship_tracker(tracker: RelationshipTracker) -> None:
    """Inject a host-provided RelationshipTracker."""
    global _relationship_tracker
    _relationship_tracker = tracker
