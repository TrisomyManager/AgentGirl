"""Unified monolithic entry point for companion-ai.

Runs all modules in a single FastAPI process for local development and MVP.
Modules can still be started individually via their own main.py for microservice mode.

Usage:
    # Monolithic mode (all modules in one process)
    uvicorn main:app --reload --port 8000

    # Lite mode (no Docker, SQLite + in-memory)
    COMPANION_LITE_MODE=true uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict

# Mark monolithic mode BEFORE importing any module that uses http_client
os.environ["COMPANION_MONOLITHIC"] = "true"

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is in path
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.config import get_settings
from shared.database import close_database, init_database_schema
from core_orchestrator.http_client import attach_monolithic_app

settings = get_settings()
logger = structlog.get_logger("companion.main")

# ---------------------------------------------------------------------------
# Module registry — which modules to enable in monolithic mode
# ---------------------------------------------------------------------------

_ENABLED_MODULES: Dict[str, bool] = {
    "gateway_adapter": True,      # Frontend WebSocket + REST entry point
    "core_orchestrator": True,    # LangGraph state machine
    "persona_engine": True,       # Personality + emotion
    "memory_system": True,        # Vector memory
    "voice_layer": settings.enable_voice,
    "action_layer": settings.enable_action_2d,
    "device_coordination": settings.enable_device_coordination and not settings.lite_mode,
}

logger.info("monolithic_modules", modules={k: v for k, v in _ENABLED_MODULES.items()})


# ---------------------------------------------------------------------------
# Lifespan: start all enabled modules
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown all enabled modules."""
    logger.info("monolithic_startup_begin", lite_mode=settings.lite_mode)

    # 1. Initialize shared database
    try:
        await init_database_schema()
        logger.info("database_ready")
    except Exception as exc:
        logger.warning("database_init_failed", error=str(exc))

    # 2. Start each module
    if _ENABLED_MODULES.get("persona_engine"):
        try:
            from persona_engine.main import lifespan as persona_lifespan
            app.state.persona_ctx = persona_lifespan(app)
            await app.state.persona_ctx.__aenter__()
            logger.info("persona_engine_ready")
        except Exception as exc:
            logger.warning("persona_engine_startup_failed", error=str(exc))

    if _ENABLED_MODULES.get("memory_system"):
        try:
            from memory_system.main import lifespan as memory_lifespan
            app.state.memory_ctx = memory_lifespan(app)
            await app.state.memory_ctx.__aenter__()
            logger.info("memory_system_ready")
        except Exception as exc:
            logger.warning("memory_system_startup_failed", error=str(exc))

    if _ENABLED_MODULES.get("voice_layer"):
        try:
            from voice_layer.main import lifespan as voice_lifespan
            app.state.voice_ctx = voice_lifespan(app)
            await app.state.voice_ctx.__aenter__()
            logger.info("voice_layer_ready")
        except Exception as exc:
            logger.warning("voice_layer_startup_failed", error=str(exc))

    if _ENABLED_MODULES.get("action_layer"):
        try:
            from action_layer.main import lifespan as action_lifespan
            app.state.action_ctx = action_lifespan(app)
            await app.state.action_ctx.__aenter__()
            logger.info("action_layer_ready")
        except Exception as exc:
            logger.warning("action_layer_startup_failed", error=str(exc))

    if _ENABLED_MODULES.get("device_coordination"):
        try:
            from device_coordination.main import lifespan as device_lifespan
            app.state.device_ctx = device_lifespan(app)
            await app.state.device_ctx.__aenter__()
            logger.info("device_coordination_ready")
        except Exception as exc:
            logger.warning("device_coordination_startup_failed", error=str(exc))

    if _ENABLED_MODULES.get("core_orchestrator"):
        try:
            from core_orchestrator.main import lifespan as orchestrator_lifespan
            app.state.orch_ctx = orchestrator_lifespan(app)
            await app.state.orch_ctx.__aenter__()
            logger.info("core_orchestrator_ready")
        except Exception as exc:
            logger.warning("core_orchestrator_startup_failed", error=str(exc))

    if _ENABLED_MODULES.get("gateway_adapter"):
        try:
            from gateway_adapter.main import lifespan as gateway_lifespan
            app.state.gateway_ctx = gateway_lifespan(app)
            await app.state.gateway_ctx.__aenter__()
            logger.info("gateway_adapter_ready")
        except Exception as exc:
            logger.warning("gateway_adapter_startup_failed", error=str(exc))

    logger.info("monolithic_startup_complete")
    yield

    # Shutdown in reverse order
    logger.info("monolithic_shutdown_begin")

    for module_name, ctx_attr in [
        ("gateway_adapter", "gateway_ctx"),
        ("core_orchestrator", "orch_ctx"),
        ("device_coordination", "device_ctx"),
        ("action_layer", "action_ctx"),
        ("voice_layer", "voice_ctx"),
        ("memory_system", "memory_ctx"),
        ("persona_engine", "persona_ctx"),
    ]:
        if hasattr(app.state, ctx_attr):
            try:
                ctx = getattr(app.state, ctx_attr)
                await ctx.__aexit__(None, None, None)
                logger.info(f"{module_name}_shutdown")
            except Exception as exc:
                logger.warning(f"{module_name}_shutdown_failed", error=str(exc))

    await close_database()
    logger.info("monolithic_shutdown_complete")


# ---------------------------------------------------------------------------
# Build the unified FastAPI app
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title="Companion AI — Unified",
        description="All companion-ai modules running in a single process.",
        version="0.1.0",
        lifespan=lifespan,
    )

    attach_monolithic_app(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers from all enabled modules
    routers = []

    if _ENABLED_MODULES.get("gateway_adapter"):
        try:
            from gateway_adapter.api import router as gateway_router
            routers.append(gateway_router)
        except Exception as exc:
            logger.warning("gateway_router_load_failed", error=str(exc))

    if _ENABLED_MODULES.get("core_orchestrator"):
        try:
            from core_orchestrator.api import router as orchestrator_router
            routers.append(orchestrator_router)
        except Exception as exc:
            logger.warning("orchestrator_router_load_failed", error=str(exc))

    if _ENABLED_MODULES.get("persona_engine"):
        try:
            from persona_engine.api import router as persona_router
            routers.append(persona_router)
        except Exception as exc:
            logger.warning("persona_router_load_failed", error=str(exc))

    if _ENABLED_MODULES.get("memory_system"):
        try:
            from memory_system.api import router as memory_router
            routers.append(memory_router)
        except Exception as exc:
            logger.warning("memory_router_load_failed", error=str(exc))

    if _ENABLED_MODULES.get("voice_layer"):
        try:
            from voice_layer.api import router as voice_router
            routers.append(voice_router)
        except Exception as exc:
            logger.warning("voice_router_load_failed", error=str(exc))

    if _ENABLED_MODULES.get("action_layer"):
        try:
            from action_layer.api import router as action_router
            routers.append(action_router)
        except Exception as exc:
            logger.warning("action_router_load_failed", error=str(exc))

    if _ENABLED_MODULES.get("device_coordination"):
        try:
            from device_coordination.api import router as device_router
            routers.append(device_router)
        except Exception as exc:
            logger.warning("device_router_load_failed", error=str(exc))

    for router in routers:
        app.include_router(router)
        logger.info("router_included", router=router.prefix or "/")

    @app.get("/", tags=["health"])
    async def root() -> Dict[str, Any]:
        return {
            "service": "companion-ai-unified",
            "status": "ok",
            "version": "0.1.0",
            "modules": {k: v for k, v in _ENABLED_MODULES.items()},
            "lite_mode": settings.lite_mode,
        }

    @app.get("/health", tags=["health"])
    async def health() -> Dict[str, Any]:
        return {
            "status": "healthy",
            "service": "companion-ai-unified",
            "timestamp": datetime.utcnow().isoformat(),
            "modules": {k: v for k, v in _ENABLED_MODULES.items()},
        }

    return app


app = create_app()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_level=settings.log_level.lower())
