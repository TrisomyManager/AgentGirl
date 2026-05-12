"""Abstract stores — swap Lite in-memory for PostgreSQL in production."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class DeviceCommandStore(ABC):
    """Command lifecycle persistence (PostgreSQL implementation: TODO in stores/postgres.py)."""

    @abstractmethod
    async def create(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new command record."""

    @abstractmethod
    async def get(self, command_id: str) -> Optional[Dict[str, Any]]:
        """Fetch command by id."""

    @abstractmethod
    async def update(self, command_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Merge patch into command; return updated dict or None if missing."""

    @abstractmethod
    async def list_for_user(self, user_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        """Recent commands for a user (newest first)."""

    @abstractmethod
    async def list_non_terminal(self) -> List[Dict[str, Any]]:
        """For timeout scanner — commands not in a final state."""

    @abstractmethod
    async def find_next_delivered(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Oldest delivered, non-expired command for device (claim_next)."""


class DeviceAuditStore(ABC):
    """Append-only audit trail (PostgreSQL implementation: TODO in stores/postgres.py)."""

    @abstractmethod
    async def append(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Persist one audit row; return entry including any server-assigned fields."""

    @abstractmethod
    async def list_for_scope(
        self,
        *,
        user_id: Optional[str] = None,
        device_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Filter audit entries (newest first)."""
