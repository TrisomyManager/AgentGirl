"""Standalone FastAPI app for action_executor.action2d (port 8004).

P2 物理搬迁完成 (V2.1). 在 monolithic 模式下由 ``main.py`` 直接复用本模块的
``lifespan`` + ``router``; 单独微服务部署时仍可以 ``python -m action_executor.action2d.main``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from shared_runtime.config import get_settings

from action_executor.action2d import api as api_mod
from action_executor.action2d.api import router
from action_executor.action2d.generator_2d import Action2DGenerator  # noqa: F401 — kept for parity
from action_executor.action2d.lip_sync import LipSyncGenerator
from action_executor.action2d.router import ActionRouter
from action_executor.action2d.sequencer import ActionSequencer

logger = structlog.get_logger("action_executor.action2d.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("action2d.startup")

    seq = ActionSequencer()
    act_router = ActionRouter()
    lip_gen = LipSyncGenerator()

    api_mod.sequencer = seq
    api_mod.router_instance = act_router
    api_mod.lip_sync_generator = lip_gen

    yield

    await seq.close()
    logger.info("action2d.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Companion AI — Action 2D",
        description="2D photo-driven action generation, lip sync, and sequencing",
        version="0.3.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "action_executor.action2d.main:app",
        host="0.0.0.0",
        port=8004,
        log_level=settings.log_level.lower(),
        reload=False,
    )
