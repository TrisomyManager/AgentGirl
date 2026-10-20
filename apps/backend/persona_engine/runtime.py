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

import structlog

from persona_engine.emotion_engine import EmotionEngine
from persona_engine.relationship_tracker import RelationshipTracker

logger = structlog.get_logger("persona_engine.runtime")

_emotion_engine: EmotionEngine | None = None
_relationship_tracker: RelationshipTracker | None = None
_state_store = None


def get_state_store():
    global _state_store
    if _state_store is None:
        from persona_engine.state_store import PersonaStateStore
        from shared_runtime.database import AsyncSessionLocal

        _state_store = PersonaStateStore(AsyncSessionLocal)
    return _state_store


def get_emotion_engine() -> EmotionEngine:
    """Return the process-level EmotionEngine singleton.

    SQLite and PostgreSQL use the same durable state store. Hosts can inject
    a custom engine, including a transient engine for an SDK prototype.
    """
    global _emotion_engine
    if _emotion_engine is None:
        _emotion_engine = EmotionEngine(state_store=get_state_store())
        logger.info("emotion_engine.created", backend="sql")
    return _emotion_engine


def get_relationship_tracker() -> RelationshipTracker:
    """Return the process-level RelationshipTracker singleton.

    The reference host uses SQL in both modes. Other hosts can inject their
    own tracker through ``set_relationship_tracker``.
    """
    global _relationship_tracker
    if _relationship_tracker is None:
        try:
            from shared_runtime.database import AsyncSessionLocal

            _relationship_tracker = RelationshipTracker(
                redis_client=None,
                db_pool=None,
                sqlite_session_factory=AsyncSessionLocal,
                state_store=get_state_store(),
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


def get_reaction_service():
    from persona_engine.reaction_service import ReactionService

    return ReactionService(get_emotion_engine(), get_relationship_tracker())
