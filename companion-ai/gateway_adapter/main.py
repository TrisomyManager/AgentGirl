"""FastAPI app for gateway_adapter (port 8006)."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict

import structlog
from fastapi import FastAPI

from shared.config import get_settings
from shared.models import Platform

from .api import router, set_dependencies
from .event_consumer import GatewayEventConsumer
from .session_manager import SessionManager
from .platforms import (
    AppWebSocketAdapter,
    DiscordAdapter,
    TelegramAdapter,
    WeChatAdapter,
)

logger = structlog.get_logger(__name__)


def _build_adapters(settings) -> Dict[Platform, any]:  # type: ignore[no-untyped-def]
    adapters: Dict[Platform, any] = {}  # type: ignore[no-untyped-def]

    # Telegram
    if settings.telegram_bot_token:
        adapters[Platform.TELEGRAM] = TelegramAdapter(
            {"bot_token": settings.telegram_bot_token}
        )

    # Discord
    if settings.discord_webhook_url:
        adapters[Platform.DISCORD] = DiscordAdapter(
            {"webhook_url": settings.discord_webhook_url}
        )

    # WeChat
    if settings.wechat_corp_id:
        adapters[Platform.WECHAT] = WeChatAdapter(
            {
                "corp_id": settings.wechat_corp_id,
                "agent_id": settings.wechat_agent_id,
                "secret": settings.wechat_secret,
            }
        )

    # App WebSocket (always enabled)
    app_ws = AppWebSocketAdapter({})
    adapters[Platform.APP] = app_ws

    return adapters, app_ws


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(__import__("logging"), settings.log_level, 20)
        ),
    )

    # Inject extra gateway-specific settings into the base Settings object
    # (In production these would be defined in shared.config; we read from env here.)
    for attr, env_var, default in [
        ("telegram_bot_token", "COMPANION_TELEGRAM_BOT_TOKEN", None),
        ("discord_webhook_url", "COMPANION_DISCORD_WEBHOOK_URL", None),
        ("wechat_corp_id", "COMPANION_WECHAT_CORP_ID", None),
        ("wechat_agent_id", "COMPANION_WECHAT_AGENT_ID", None),
        ("wechat_secret", "COMPANION_WECHAT_SECRET", None),
    ]:
        if not hasattr(settings, attr):
            import os
            setattr(settings, attr, os.environ.get(env_var, default))

    sessions = SessionManager()
    adapters, app_ws = _build_adapters(settings)

    consumer: Optional[GatewayEventConsumer] = None
    if not settings.lite_mode:
        consumer = GatewayEventConsumer(adapter_registry=adapters, session_manager=sessions)
        await consumer.start()
        logger.info("gateway_adapter.consumer_started")
    else:
        logger.info("gateway_adapter.lite_mode_skip_consumer")

    set_dependencies(consumer, sessions, adapters, app_ws)
    logger.info("gateway_adapter.started", port=settings.service_port, platforms=list(adapters.keys()))

    yield

    if consumer:
        await consumer.stop()
    for adapter in adapters.values():
        if hasattr(adapter, "_client") and hasattr(adapter._client, "aclose"):
            await adapter._client.aclose()
    logger.info("gateway_adapter.stopped")


app = FastAPI(
    title="Gateway Adapter",
    version="0.2.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "gateway_adapter"}
