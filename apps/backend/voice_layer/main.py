"""voice_layer FastAPI application — runs on port 8003."""

from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from shared_runtime.config import get_settings
from shared_runtime.voice_runtime_config import load_voice_config_from_disk
from voice_layer.api import router
from voice_layer.asr_runtime import ASRFactory
from voice_layer.tts import TTSClient
from voice_layer.voice_static import mount_voice_static_files

logger = structlog.get_logger("voice_layer.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown shared clients."""
    logger.info("voice_layer.startup")

    # Load runtime voice config from disk BEFORE creating clients
    load_voice_config_from_disk()

    # Initialize clients
    tts = TTSClient()

    # Inject into router module
    import voice_layer.api as api_mod

    api_mod.tts_client = tts

    try:
        yield
    finally:
        await tts.close()
        logger.info("voice_layer.shutdown")


def create_app(*, asr_factory: ASRFactory | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Companion AI — Voice Layer",
        description="ASR, TTS, and real-time voice streaming",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.state.voice_asr_factory = asr_factory
    mount_voice_static_files(app)
    app.include_router(router)
    return app


app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "voice_layer.main:app",
        host="0.0.0.0",
        port=8003,
        log_level=settings.log_level.lower(),
        reload=False,
    )
