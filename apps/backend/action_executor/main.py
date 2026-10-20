"""action_executor FastAPI application — runs on port 8007.

In Lite Mode this is hosted by the unified ``main.py`` (port 8000);
the standalone microservice form is provided here so the action
executor can also be split out independently if needed later.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import uvicorn
from fastapi import FastAPI

from action_executor import handlers  # noqa: F401 — register builtins
from action_executor.api import router
from action_executor.proactive_care import ProactiveLogORM  # noqa: F401 — register ORM table
from action_executor.reminders import get_reminder_scheduler
from shared_runtime.config import get_settings
from shared_runtime.database import init_database_schema

logger = structlog.get_logger("action_executor.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("action_executor.startup")
    try:
        await init_database_schema()
    except Exception as exc:
        logger.warning("action_executor.schema_init_failed", error=str(exc))

    settings = get_settings()
    from action_executor.mcp_client import mcp_hub
    from action_executor.task_agent import task_agent
    from action_executor.task_store import task_store

    await task_store.recover_interrupted()
    from action_executor.plugins import plugin_manager

    backend_root = Path(__file__).resolve().parent.parent
    plugin_dir = Path(os.environ.get("COMPANION_PLUGINS_DIR") or settings.plugins_dir or "plugins")
    plugin_manager.directory = plugin_dir if plugin_dir.is_absolute() else backend_root / plugin_dir
    plugin_file = os.environ.get("COMPANION_PLUGINS_CONFIG_FILE") or settings.plugins_config_file
    config_path = Path(plugin_file) if plugin_file else None
    plugin_manager.config_file = (
        backend_root / config_path if config_path and not config_path.is_absolute() else config_path
    )
    mcp_config = (os.environ.get("COMPANION_MCP_CONFIG_FILE") or settings.mcp_config_file or "").strip()
    if mcp_config:
        try:
            mcp_hub.load_file(mcp_config)
        except Exception:
            logger.warning("action_executor.mcp_configuration_invalid")

    scheduler = get_reminder_scheduler()
    proactive_scheduler = None
    try:
        await plugin_manager.start()
        await scheduler.start()
        if settings.proactive_enabled:
            from action_executor.proactive_care import get_proactive_care_scheduler

            proactive_scheduler = get_proactive_care_scheduler(
                poll_interval=settings.proactive_poll_interval_seconds,
            )
            await proactive_scheduler.start()
        yield
    finally:
        await task_agent.close()
        await plugin_manager.close()
        await mcp_hub.close()
        await scheduler.stop()
        if proactive_scheduler is not None:
            await proactive_scheduler.stop()
        logger.info("action_executor.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Companion AI — Action Executor",
        description=(
            "Pluggable action handlers (reminders, time, weather stub) plus an SSE stream for proactive push events."
        ),
        version="0.2.0",
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
