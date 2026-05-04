"""Base platform adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class BasePlatformAdapter(ABC):
    """Abstract base for all platform adapters.

    New platforms can be added by subclassing and implementing
    `send_message` and `broadcast`.
    """

    def __init__(self, platform_name: str, config: Dict[str, Any]) -> None:
        self.platform_name = platform_name
        self.config = config
        self._logger = logger.bind(platform=platform_name)

    @abstractmethod
    async def send_message(
        self,
        user_id: str,
        content: str,
        media: Optional[Dict[str, Any]] = None,
        reply_to_message_id: Optional[str] = None,
    ) -> Optional[str]:
        """Send a message to a specific user on this platform.

        Returns the platform-specific message ID if available.
        """

    @abstractmethod
    async def broadcast(
        self,
        user_id: str,
        content: str,
    ) -> None:
        """Broadcast a message to all sessions for this user on this platform."""

    async def health_check(self) -> bool:
        """Optional health check. Override if the platform supports it."""
        return True
