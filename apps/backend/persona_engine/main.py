"""FastAPI application for persona_engine (port 8001).

Lifespan:
- Loads the soul YAML into app.state.
- Initialises Redis and PostgreSQL connections.
- Sets up the EmotionEngine, RelationshipTracker, and ToneGenerator.
- Gracefully tears down connections on exit.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI

# Ensure shared/ is importable when running from the persona_engine directory
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared_runtime.config import get_settings
from shared_contracts.models import PersonaProfile

from persona_engine.api import router
from shared_runtime.llm_client import LLMClient

from persona_engine.emotion_engine import EmotionEngine
from persona_engine.persona_store import get_persona_profile
from persona_engine.relationship_tracker import RelationshipTracker
from persona_engine.tone_generator import ToneGenerator

logger = structlog.get_logger("persona_engine.main")

# ---------------------------------------------------------------------------
# Service state container
# ---------------------------------------------------------------------------

class ServiceState:
    """Holds runtime references to external resources."""

    def __init__(self) -> None:
        self.redis = None
        self.db_pool = None
        self.persona: PersonaProfile | None = None
        self.emotion_engine: EmotionEngine | None = None
        self.relationship_tracker: RelationshipTracker | None = None
        self.tone_generator: ToneGenerator | None = None
        self.llm_client: LLMClient | None = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown logic."""
    settings = get_settings()
    state = ServiceState()

    # -- Startup ---------------------------------------------------------
    logger.info("lifespan.startup", service="persona_engine", port=settings.service_port)

    # 1. Load persona (sync, cached)
    state.persona = get_persona_profile()
    logger.info("lifespan.persona_loaded", name=state.persona.name)

    # 2. Redis (best-effort — service can run without it for local dev)
    try:
        import redis.asyncio as aioredis
        state.redis = await aioredis.from_url(
            settings.redis_url,
            decode_responses=False,
            socket_connect_timeout=5,
        )
        await state.redis.ping()
        logger.info("lifespan.redis_connected", url=settings.redis_url)
    except Exception as exc:
        logger.warning("lifespan.redis_failed", error=str(exc))
        state.redis = None

    # 3. PostgreSQL (best-effort)
    try:
        import asyncpg
        state.db_pool = await asyncpg.create_pool(
            dsn=settings.postgres_url,
            min_size=1,
            max_size=5,
            command_timeout=10,
        )
        logger.info("lifespan.postgres_connected", url=settings.postgres_url)

        # Ensure relationship_metrics table exists
        async with state.db_pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS relationship_metrics (
                    user_id TEXT PRIMARY KEY,
                    intimacy DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    trust DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    familiarity DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    affection DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    total_interactions INTEGER NOT NULL DEFAULT 0,
                    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        logger.info("lifespan.db_migrated")
    except Exception as exc:
        logger.warning("lifespan.postgres_failed", error=str(exc))
        state.db_pool = None

    # 4. Engines
    state.emotion_engine = EmotionEngine(redis_client=state.redis)
    # In lite mode, pass SQLite session factory to RelationshipTracker
    if settings.lite_mode:
        from shared.database import AsyncSessionLocal
        sqlite_session_factory = AsyncSessionLocal
    else:
        sqlite_session_factory = None
    state.relationship_tracker = RelationshipTracker(
        redis_client=state.redis,
        db_pool=state.db_pool,
        sqlite_session_factory=sqlite_session_factory,
    )
    state.tone_generator = ToneGenerator(persona=state.persona)
    state.llm_client = LLMClient()

    app.state.emotion_engine = state.emotion_engine
    app.state.relationship_tracker = state.relationship_tracker
    app.state.tone_generator = state.tone_generator
    app.state.llm_client = state.llm_client
    app.state.redis = state.redis
    app.state.db_pool = state.db_pool

    logger.info("lifespan.ready")
    yield

    # -- Shutdown --------------------------------------------------------
    logger.info("lifespan.shutdown")
    if state.llm_client:
        await state.llm_client.close()
        logger.info("lifespan.llm_client_closed")
    if state.redis:
        await state.redis.close()
        logger.info("lifespan.redis_closed")
    if state.db_pool:
        await state.db_pool.close()
        logger.info("lifespan.postgres_closed")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Application factory — used by uvicorn and tests."""
    app = FastAPI(
        title="Persona Engine",
        description="Structured persona, emotion state machine, relationship tracking, and dynamic tone generation for companion-ai.",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "persona_engine"}

    return app


app = create_app()

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    settings = get_settings()
    # persona_engine runs on port 8001 per architecture doc
    port = 8001 if settings.service_port == 8000 else settings.service_port
    uvicorn.run(
        "persona_engine.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
