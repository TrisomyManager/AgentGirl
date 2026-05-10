"""FastAPI app for device_coordination (port 8005)."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI

from shared_runtime.config import get_settings
from shared_contracts.events import DeviceHeartbeatEvent

from .api import router, set_dependencies
from .mqtt_client import DeviceMQTTClient
from .registry import DeviceRegistry
from .task_dispatcher import TaskDispatcher

logger = structlog.get_logger(__name__)


async def _on_heartbeat(event: DeviceHeartbeatEvent) -> None:
    """Handle MQTT heartbeat: update registry."""
    registry = DeviceRegistry()
    await registry.heartbeat(
        event.device_info.device_id,
        ip_address=event.device_info.ip_address,
    )
    logger.debug("main.mqtt_heartbeat_handled", device_id=event.device_info.device_id)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(getattr(__import__("logging"), settings.log_level, 20)),
    )

    registry = DeviceRegistry()
    await registry.start()

    mqtt: Optional[DeviceMQTTClient] = None
    if not settings.lite_mode:
        mqtt = DeviceMQTTClient(on_heartbeat=_on_heartbeat)
        await mqtt.start()
        logger.info("device_coordination.mqtt_started")
    else:
        logger.info("device_coordination.lite_mode_skip_mqtt")

    dispatcher = TaskDispatcher(registry)

    set_dependencies(registry, mqtt, dispatcher)
    logger.info("device_coordination.started", port=settings.service_port)

    yield

    if mqtt:
        await mqtt.stop()
    await registry.stop()
    logger.info("device_coordination.stopped")


app = FastAPI(
    title="Device Coordination",
    version="0.2.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "device_coordination"}
