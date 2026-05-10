"""FastAPI application entry point for core_orchestrator (port 8000)."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared_runtime.config import get_settings
from shared_runtime.llm_client import load_llm_config_from_disk
from shared_runtime.voice_runtime_config import load_voice_config_from_disk

from core_orchestrator.api import router as orchestrator_router
from core_orchestrator.event_bus import shutdown_event_bus
from core_orchestrator.http_client import close_all
from core_orchestrator.orchestrator import get_orchestrator, shutdown_orchestrator

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Structured logging setup
# ---------------------------------------------------------------------------


def configure_logging(log_level: str) -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


# ---------------------------------------------------------------------------
# Lifespan manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("app_startup_begin", service=settings.service_name, port=settings.service_port)

    # Restore LLM config saved from a previous run
    load_llm_config_from_disk()
    load_voice_config_from_disk()

    # Initialize orchestrator (connects Redis, compiles graph, checks services)
    try:
        orch = await get_orchestrator()
        logger.info("app_orchestrator_ready")
    except Exception as exc:
        logger.error("app_startup_failed", error=str(exc))
        raise

    yield

    # Shutdown
    logger.info("app_shutdown_begin")
    await shutdown_orchestrator()
    await shutdown_event_bus()
    await close_all()
    logger.info("app_shutdown_complete")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

settings = get_settings()
app = FastAPI(
    title="Companion AI — Core Orchestrator",
    description="LangGraph-based central orchestration service for companion-ai.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orchestrator_router)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Root / health
# ---------------------------------------------------------------------------


@app.get("/", tags=["health"])
async def root() -> Dict[str, str]:
    return {"service": "core_orchestrator", "status": "ok"}


@app.get("/health", tags=["health"])
async def health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": "0.2.0",
        "timestamp": datetime.utcnow().isoformat(),
    }
