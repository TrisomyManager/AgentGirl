"""PostgreSQL-backed device gateway stores (placeholder for production).

TODO: Implement asyncpg-backed DeviceCommandStore and DeviceAuditStore using
companion-ai shared database or a dedicated device_gateway schema. Include
migrations for commands, command_state_history, and audit_log tables.
"""

from __future__ import annotations

# Intentionally empty — production wiring is out of scope for this iteration.

__all__: list[str] = []
