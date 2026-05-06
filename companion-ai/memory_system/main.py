"""FastAPI application for memory_system microservice (port 8002)."""

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI

from shared.config import get_settings

from memory_system.api import router as memory_router
from memory_system.db import close_engine, init_schema
from memory_system.graph_store import graph_store
from memory_system.short_term import close_redis

logger = structlog.get_logger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init schema and connections on startup."""
    logger.info("memory_system.starting", service="memory_system", port=8002)

    # PostgreSQL + pgvector
    await init_schema()

    # Neo4j (skip in lite mode)
    if settings.enable_knowledge_graph and not settings.lite_mode:
        await graph_store.connect()
        await graph_store.init_schema()

    logger.info("memory_system.ready")
    yield

    # Shutdown
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
