"""action_layer FastAPI application — runs on port 8004."""

from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from shared.config import get_settings
from action_layer.api import lip_sync_generator, router, router_instance, sequencer
from action_layer.generator_2d import Action2DGenerator
from action_layer.lip_sync import LipSyncGenerator
from action_layer.router import ActionRouter
from action_layer.sequencer import ActionSequencer

logger = structlog.get_logger("action_layer.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown shared components."""
    logger.info("action_layer.startup")

    # Initialize components
    seq = ActionSequencer()
    act_router = ActionRouter()
    lip_gen = LipSyncGenerator()

    # Inject into router module
    import action_layer.api as api_mod

    api_mod.sequencer = seq
    api_mod.router_instance = act_router
    api_mod.lip_sync_generator = lip_gen

    yield

    # Teardown
    await seq.close()
    logger.info("action_layer.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Companion AI — Action Layer",
        description="2D photo-driven action generation, lip sync, and sequencing",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "action_layer.main:app",
        host="0.0.0.0",
        port=8004,
        log_level=settings.log_level.lower(),
        reload=False,
    )
