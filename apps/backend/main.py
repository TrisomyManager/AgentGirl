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

import os
import sys
from contextlib import asynccontextmanager
from collections.abc import Callable
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

from core_orchestrator.http_client import attach_monolithic_app
from shared_runtime.config import get_settings
from shared_runtime.database import close_database, init_database_schema
from shared_contracts.protocols import SpeechRecognizer

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
    "action_executor": True,      # Reminders / time / weather (pluggable handlers)
    "device_coordination": True,  # always on; Lite Mode uses in-memory store
}

logger.info("monolithic_modules", modules={k: v for k, v in _ENABLED_MODULES.items()})


# ---------------------------------------------------------------------------
# Lifespan: start all enabled modules
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Own successfully started resources, fail startup on required module errors."""
    from contextlib import AsyncExitStack
    from importlib import import_module

    from core_orchestrator.privacy import no_pending_erasure
    from core_orchestrator.platforms import platform_lifespan
    from shared_runtime.user_lifecycle import set_user_admission_check
    from user_profile import get_default_store

    app.state.ready = False
    app.state.startup_modules = {"database": "starting"}
    access = app.state.access_controller
    if access.mode == "key":
        access._reload()
        if not access._valid:
            raise RuntimeError("Host access configuration is invalid")
    modules = [
        ("persona_engine", "persona_engine.main"),
        ("memory_system", "memory_system.main"),
        ("voice_layer", "voice_layer.main"),
        ("action_layer", "action_executor.action2d.main"),
        ("action_executor", "action_executor.main"),
        ("device_coordination", "device_coordination.main"),
        ("core_orchestrator", "core_orchestrator.main"),
        ("gateway_adapter", "gateway_adapter.main"),
    ]
    try:
        get_default_store()
        await init_database_schema()
        app.state.startup_modules["database"] = "ready"
        set_user_admission_check(no_pending_erasure)
        async with AsyncExitStack() as resources:
            for name, module_path in modules:
                if not _ENABLED_MODULES.get(name):
                    continue
                app.state.startup_modules[name] = "starting"
                try:
                    factory = import_module(module_path).lifespan
                    await resources.enter_async_context(factory(app))
                except Exception as error:
                    app.state.startup_modules[name] = "failed"
                    logger.error("module_startup_failed", module=name, reason=type(error).__name__)
                    raise
                app.state.startup_modules[name] = "ready"
            if _ENABLED_MODULES.get("gateway_adapter") and _ENABLED_MODULES.get("core_orchestrator"):
                await resources.enter_async_context(platform_lifespan(app))
            app.state.ready = True
            logger.info("monolithic_startup_complete")
            try:
                yield
            finally:
                app.state.ready = False
    finally:
        app.state.ready = False
        from voice_layer.text_policy import set_text_policy
        from action_executor.task_agent import task_agent

        set_text_policy()
        task_agent.request_filter = None
        task_agent.response_filter = None
        from action_executor.memory_port import set_memory_reader

        set_memory_reader(None)
        set_user_admission_check(None)
        await close_database()
        logger.info("monolithic_shutdown_complete")


# ---------------------------------------------------------------------------
# Build the unified FastAPI app
# ---------------------------------------------------------------------------


def create_app(*, asr_factory: Callable[[], SpeechRecognizer] | None = None) -> FastAPI:
    app = FastAPI(
        title="Companion AI — Unified",
        description="All companion-ai modules running in a single process.",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.state.ready = False
    app.state.voice_asr_factory = asr_factory
    app.state.startup_modules = {}
    attach_monolithic_app(app)
    from core_orchestrator.access_policy import HostAccessPolicy
    from shared_runtime.access import AccessController, AccessMiddleware, access_router, attach_reference_app

    access_path = Path(settings.access_config_file) if settings.access_config_file else None
    if access_path and not access_path.is_absolute():
        access_path = _PROJECT_ROOT / access_path
    access = AccessController(access_path, origins=[value.strip() for value in settings.cors_origins.split(",")])
    app.state.access_controller = access
    app.include_router(access_router(access))
    from core_orchestrator.privacy import router as privacy_router
    from gateway_adapter import store as _platform_store  # noqa: F401 -- register before schema startup
    app.include_router(privacy_router)
    from core_orchestrator.admin import router as admin_router
    app.include_router(admin_router)
    attach_reference_app(app)
    app.add_middleware(AccessMiddleware, controller=access, authorize=HostAccessPolicy(app, access))

    # Parse CORS origins from settings (comma-separated)
    _raw_cors = settings.cors_origins.strip()
    if _raw_cors == "*":
        _allow_origins = ["*"]
    else:
        _allow_origins = [o.strip() for o in _raw_cors.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allow_origins,
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
    else:
        try:
            from voice_layer.disabled_stub import router as voice_disabled_router

            routers.append(voice_disabled_router)
            logger.info("voice_layer_stub_router_enabled")
        except Exception as exc:
            logger.warning("voice_disabled_router_load_failed", error=str(exc))

    if _ENABLED_MODULES.get("action_layer"):
        try:
            from action_executor.action2d.api import router as action_router
            routers.append(action_router)
        except Exception as exc:
            logger.warning("action_router_load_failed", error=str(exc))

    if _ENABLED_MODULES.get("action_executor"):
        try:
            from action_executor.api import router as action_executor_router
            routers.append(action_executor_router)
        except Exception as exc:
            logger.warning("action_executor_router_load_failed", error=str(exc))

    if _ENABLED_MODULES.get("device_coordination"):
        try:
            from device_coordination.api import router as device_router
            routers.append(device_router)
        except Exception as exc:
            logger.warning("device_router_load_failed", error=str(exc))

    for router in routers:
        app.include_router(router)
        logger.info("router_included", router=router.prefix or "/")

    from voice_layer.voice_static import mount_voice_static_files

    mount_voice_static_files(app)

    @app.get("/", tags=["health"])
    async def root() -> Dict[str, Any]:
        voice_on = bool(_ENABLED_MODULES.get("voice_layer"))
        return {
            "service": "companion-ai-unified",
            "status": "ok",
            "version": "0.2.0",
            "modules": {k: v for k, v in _ENABLED_MODULES.items()},
            "lite_mode": settings.lite_mode,
            "voice": {
                "enabled": voice_on,
                "hint": None
                if voice_on
                else (
                    "语音未启用：设置 COMPANION_ENABLE_VOICE=true 或 "
                    "python scripts/start_lite_server.py --voice"
                ),
            },
        }

    @app.get("/health", tags=["health"])
    async def health() -> Dict[str, Any]:
        from starlette.responses import JSONResponse

        voice_on = bool(_ENABLED_MODULES.get("voice_layer"))
        payload = {
            "status": "healthy" if app.state.ready else "starting",
            "startup": dict(app.state.startup_modules),
            "service": "companion-ai-unified",
            "timestamp": datetime.utcnow().isoformat(),
            "modules": {k: v for k, v in _ENABLED_MODULES.items()},
            "voice": {
                "enabled": voice_on,
                "hint": None
                if voice_on
                else (
                    "语音路由已关闭。请设置 COMPANION_ENABLE_VOICE=true 或使用 "
                    "python scripts/start_lite_server.py --voice"
                ),
            },
        }
        return JSONResponse(payload, status_code=200 if app.state.ready else 503)

    return app


app = create_app()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_level=settings.log_level.lower())
