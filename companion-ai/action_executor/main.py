"""action_executor FastAPI application — runs on port 8007.

In Lite Mode this is hosted by the unified ``main.py`` (port 8000);
the standalone microservice form is provided here so the action
executor can also be split out independently if needed later.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from action_executor import handlers  # noqa: F401 — register builtins
from action_executor.api import router
from action_executor.reminders import get_reminder_scheduler
from shared.config import get_settings
from shared.database import init_database_schema

logger = structlog.get_logger("action_executor.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("action_executor.startup")
    try:
        await init_database_schema()
    except Exception as exc:
        logger.warning("action_executor.schema_init_failed", error=str(exc))

    scheduler = get_reminder_scheduler()
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()
        logger.info("action_executor.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Companion AI — Action Executor",
        description=(
            "Pluggable action handlers (reminders, time, weather stub) plus "
            "an SSE stream for proactive push events."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "action_executor.main:app",
        host="0.0.0.0",
        port=8007,
        log_level=settings.log_level.lower(),
        reload=False,
    )
