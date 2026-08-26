"""FastAPI app for device_coordination (port 8005)."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import structlog
from fastapi import FastAPI

from shared_contracts.events import DeviceHeartbeatEvent
from shared_runtime.config import get_settings

from .api import router, set_dependencies
from .gateway_service import DeviceGatewayService
from .mqtt_client import DeviceMQTTClient
from .registry import DeviceRegistry
from .stores.memory import MemoryDeviceAuditStore, MemoryDeviceCommandStore
from .task_dispatcher import TaskDispatcher
from .transport.mqtt_transport import MqttDeviceTransport
from .transport.polling import PollingDeviceTransport

logger = structlog.get_logger(__name__)


def _heartbeat_handler(registry: DeviceRegistry):
    async def _on_heartbeat(event: DeviceHeartbeatEvent) -> None:
        await registry.heartbeat(
            event.device_info.device_id,
            ip_address=event.device_info.ip_address,
        )
        logger.debug("main.mqtt_heartbeat_handled", device_id=event.device_info.device_id)

    return _on_heartbeat


async def _timeout_scan_loop(gateway: DeviceGatewayService) -> None:
    while True:
        try:
            await asyncio.sleep(30)
            n = await gateway.scan_timeouts()
            if n:
                logger.debug("device_gateway.timeouts_marked", count=n)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("device_gateway.timeout_scan_error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(getattr(__import__("logging"), settings.log_level, 20)),
    )

    _lite = settings.lite_mode or settings.monolithic or os.environ.get("COMPANION_MONOLITHIC", "false").lower() in ("1", "true", "yes")

    registry = DeviceRegistry()
    await registry.start()

    mqtt: Optional[DeviceMQTTClient] = None
    if not _lite:
        mqtt = DeviceMQTTClient(on_heartbeat=_heartbeat_handler(registry))
        await mqtt.start()
        logger.info("device_coordination.mqtt_started")
    else:
        logger.info("device_coordination.lite_mode_skip_mqtt")

    dispatcher = TaskDispatcher(registry)
    command_store = MemoryDeviceCommandStore()
    audit_store = MemoryDeviceAuditStore(max_entries=100)
    if mqtt is not None:
        transport: PollingDeviceTransport | MqttDeviceTransport = MqttDeviceTransport(mqtt)
    else:
        transport = PollingDeviceTransport()

    gateway = DeviceGatewayService(registry, command_store, audit_store, transport, settings=settings)
    timeout_task = asyncio.create_task(_timeout_scan_loop(gateway))

    set_dependencies(registry, mqtt, dispatcher, gateway)
    logger.info("device_coordination.started", port=settings.service_port)

    yield

    timeout_task.cancel()
    try:
        await timeout_task
    except asyncio.CancelledError:
        pass

    if mqtt:
        await mqtt.stop()
    await registry.stop()
    logger.info("device_coordination.stopped")


app = FastAPI(
    title="Device Coordination",
    version="0.3.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "device_coordination"}
