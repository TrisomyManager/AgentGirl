"""Shared async HTTP client for calling downstream companion-ai services."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from shared.config import get_settings

logger = structlog.get_logger()

_MONOLITHIC = os.environ.get("COMPANION_MONOLITHIC", "false").lower() in ("1", "true", "yes")
_BASE_PORT = int(os.environ.get("COMPANION_PORT", "8000"))
_MONOLITHIC_APP: Any | None = None

if _MONOLITHIC:
    _BASE_URL = f"http://localhost:{_BASE_PORT}"
    PERSONA_ENGINE_URL = _BASE_URL
    MEMORY_SYSTEM_URL = _BASE_URL
    VOICE_LAYER_URL = _BASE_URL
    ACTION_LAYER_URL = _BASE_URL
    DEVICE_COORDINATION_URL = _BASE_URL
    GATEWAY_ADAPTER_URL = _BASE_URL
else:
    PERSONA_ENGINE_URL = "http://localhost:8001"
    MEMORY_SYSTEM_URL = "http://localhost:8002"
    VOICE_LAYER_URL = "http://localhost:8003"
    ACTION_LAYER_URL = "http://localhost:8004"
    DEVICE_COORDINATION_URL = "http://localhost:8005"
    GATEWAY_ADAPTER_URL = "http://localhost:8006"

ALL_SERVICES: Dict[str, str] = {
    "persona_engine": PERSONA_ENGINE_URL,
    "memory_system": MEMORY_SYSTEM_URL,
    "voice_layer": VOICE_LAYER_URL,
    "action_layer": ACTION_LAYER_URL,
    "device_coordination": DEVICE_COORDINATION_URL,
    "gateway_adapter": GATEWAY_ADAPTER_URL,
}

_settings = get_settings()
if _settings.lite_mode:
    del ALL_SERVICES["device_coordination"]
    del ALL_SERVICES["gateway_adapter"]


def attach_monolithic_app(app: Any) -> None:
    """Attach the in-process FastAPI app for internal service calls."""
    global _MONOLITHIC_APP
    _MONOLITHIC_APP = app


class ServiceClient:
    """Async HTTP client wrapper with retries, structured logging, and health checks."""

    def __init__(
        self,
        base_url: str,
        service_name: str,
        timeout: float = 30.0,
        max_connections: int = 20,
    ) -> None:
        self.service_name = service_name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._limits = httpx.Limits(max_connections=max_connections)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            client_kwargs: Dict[str, Any] = {
                "timeout": httpx.Timeout(self.timeout),
                "limits": self._limits,
            }
            if _MONOLITHIC and _MONOLITHIC_APP is not None:
                client_kwargs["transport"] = httpx.ASGITransport(app=_MONOLITHIC_APP)
                client_kwargs["base_url"] = self.base_url
            self._client = httpx.AsyncClient(**client_kwargs)
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def post(
        self,
        path: str,
        json_payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        client = await self._get_client()
        url = f"{self.base_url}{path}"
        log = logger.bind(service=self.service_name, method="POST", path=path)
        log.debug("http_request_outgoing", url=url)
        try:
            response = await client.post(url, json=json_payload, params=params, headers=headers)
            response.raise_for_status()
            log.debug("http_request_success", status=response.status_code)
            return response
        except httpx.HTTPStatusError as exc:
            log.warning(
                "http_request_http_error",
                status=exc.response.status_code,
                body=exc.response.text[:500],
            )
            raise
        except (httpx.NetworkError, httpx.TimeoutException) as exc:
            log.warning("http_request_retryable_error", error=str(exc))
            raise
        except Exception as exc:
            log.error("http_request_unexpected_error", error=str(exc))
            raise

    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        client = await self._get_client()
        url = f"{self.base_url}{path}"
        log = logger.bind(service=self.service_name, method="GET", path=path)
        log.debug("http_request_outgoing", url=url)
        try:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            log.debug("http_request_success", status=response.status_code)
            return response
        except httpx.HTTPStatusError as exc:
            log.warning(
                "http_request_http_error",
                status=exc.response.status_code,
                body=exc.response.text[:500],
            )
            raise
        except (httpx.NetworkError, httpx.TimeoutException) as exc:
            log.warning("http_request_retryable_error", error=str(exc))
            raise
        except Exception as exc:
            log.error("http_request_unexpected_error", error=str(exc))
            raise

    async def health(self) -> Dict[str, Any]:
        """Return health status dict for this service."""
        try:
            resp = await self.get("/health")
            data = resp.json()
            return {
                "service": self.service_name,
                "url": self.base_url,
                "status": data.get("status", "unknown"),
                "healthy": True,
            }
        except Exception as exc:
            return {
                "service": self.service_name,
                "url": self.base_url,
                "status": f"unreachable: {exc}",
                "healthy": False,
            }

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


persona_client = ServiceClient(PERSONA_ENGINE_URL, "persona_engine")
memory_client = ServiceClient(MEMORY_SYSTEM_URL, "memory_system")
voice_client = ServiceClient(VOICE_LAYER_URL, "voice_layer")
action_client = ServiceClient(ACTION_LAYER_URL, "action_layer")
device_client = ServiceClient(DEVICE_COORDINATION_URL, "device_coordination")
gateway_client = ServiceClient(GATEWAY_ADAPTER_URL, "gateway_adapter")

ALL_CLIENTS: List[ServiceClient] = [
    persona_client,
    memory_client,
    voice_client,
    action_client,
]
if not _settings.lite_mode:
    ALL_CLIENTS.extend([device_client, gateway_client])


async def check_all_services() -> List[Dict[str, Any]]:
    """Run health checks against every downstream service concurrently."""
    results = await asyncio.gather(*[client.health() for client in ALL_CLIENTS])
    return list(results)


async def close_all() -> None:
    """Close all client connections gracefully."""
    await asyncio.gather(*[client.close() for client in ALL_CLIENTS])
