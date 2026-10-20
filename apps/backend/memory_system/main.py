"""FastAPI application for memory_system microservice (port 8002)."""

import asyncio
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import FastAPI

from memory_system.api import router as memory_router
from memory_system.db import close_engine, init_schema
from memory_system.dream import memory_maintenance
from memory_system.graph_store import graph_store
from memory_system.short_term import close_redis
from shared_runtime.config import get_settings

logger = structlog.get_logger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init schema and connections on startup."""
    logger.info("memory_system.starting", service="memory_system", port=8002)

    cleanup_task = None
    try:
        await init_schema()
        if settings.enable_knowledge_graph and not settings.lite_mode:
            await graph_store.connect()
            await graph_store.init_schema()
            from memory_system.graph_lifecycle import cleanup_worker, retry_cleanup

            cursor = await retry_cleanup()
            cleanup_task = asyncio.create_task(cleanup_worker(cursor), name="memory-graph-cleanup")
        logger.info("memory_system.ready")
        if settings.memory_maintenance_enabled:
            await memory_maintenance.start()
        yield
    finally:
        if cleanup_task is not None:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
        await memory_maintenance.stop()
        logger.info("memory_system.shutting_down")
        await close_engine()
        await close_redis()
        if settings.enable_knowledge_graph and not settings.lite_mode:
            await graph_store.close()
        logger.info("memory_system.stopped")


app = FastAPI(
    title="Companion AI — Memory System",
    description="5-stage memory pipeline, vector search, and knowledge graph.",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(memory_router)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "service": "memory_system", "version": "0.2.0"}
