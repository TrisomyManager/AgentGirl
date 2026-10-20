"""Device Operation Gateway — command lifecycle, auth checks, audit, transport."""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import structlog

from device_coordination.command_policy import valid_payload
from device_coordination.registry import DeviceRegistry
from device_coordination.stores.base import DeviceAuditStore, DeviceCommandStore
from device_coordination.transport.base import DeviceTransport
from shared_contracts.models import DeviceInfo
from shared_runtime.config import Settings, get_settings

logger = structlog.get_logger(__name__)

_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "denied", "timeout", "cancelled"})
_ACTIVE_STATUSES = frozenset({"pending", "delivered", "claimed", "running"})

_COMMAND_SPECS: Dict[str, Dict[str, Any]] = {
    "ping": {
        "risk_level": "low",
        "requires_confirmation": False,
        "description": "Ping a device to check connectivity.",
    },
    "show_notification": {
        "risk_level": "low",
        "requires_confirmation": False,
        "description": "Show a local notification on the device.",
    },
    "open_url": {
        "risk_level": "medium",
        "requires_confirmation": True,
        "description": "Open a URL on the device. Only http/https allowed.",
        "validator": lambda p: bool(re.match(r"^https?://", (p.get("url") or "").strip())),
    },
    "get_device_status": {
        "risk_level": "low",
        "requires_confirmation": False,
        "description": "Get device status (platform, time, version, capabilities).",
    },
    # High-risk placeholder — must never execute in this iteration.
    "remote_shell": {
        "risk_level": "high",
        "requires_confirmation": True,
        "description": "Reserved — blocked.",
    },
}


def _utcnow() -> datetime:
    return datetime.utcnow()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def public_device_dict(device: DeviceInfo) -> Dict[str, Any]:
    data = device.model_dump(mode="json")
    meta = dict(data.get("metadata") or {})
    meta.pop("device_token", None)
    data["metadata"] = meta
    return data


class DeviceGatewayService:
    def __init__(
        self,
        registry: DeviceRegistry,
        commands: DeviceCommandStore,
        audit: DeviceAuditStore,
        transport: DeviceTransport,
        *,
        settings: Optional[Settings] = None,
    ) -> None:
        self._registry = registry
        self._commands = commands
        self._audit = audit
        self._transport = transport
        self._settings = settings or get_settings()

    async def export_user_data(self, user_id: str):
        return {
            "devices": [public_device_dict(device) for device in await self._registry.list_for_user(user_id)],
            "commands": await self._commands.list_for_user(user_id, limit=100001),
            "audit": await self._audit.list_for_scope(user_id=user_id, limit=100001),
        }

    async def delete_user_data(self, user_id: str):
        for device in await self._registry.list_for_user(user_id):
            await self._transport.disconnect(device.device_id)
            await self._registry.unregister(device.device_id)
        await self._commands.delete_user(user_id)
        await self._audit.delete_user(user_id)

    # ------------------------------------------------------------------
    # Policy
    # ------------------------------------------------------------------

    def validate_command(self, command: str, payload: dict) -> Tuple[Dict[str, Any], Optional[str]]:
        """Return (spec, error_code). error_code set when request must be rejected."""
        spec = _COMMAND_SPECS.get(command)
        if spec is None:
            return {}, "unknown_command"
        if spec.get("risk_level") == "high":
            return spec, "high_risk_blocked"
        if not valid_payload(command, payload):
            return spec, "payload_invalid"
        validator: Optional[Callable[[dict], bool]] = spec.get("validator")
        if validator and not validator(payload):
            return spec, "payload_invalid"
        return spec, None

    def confirmation_for_user_request(self, spec: Dict[str, Any]) -> str:
        """Explicit HTTP/API send_command counts as user-approved for medium-risk."""
        if spec.get("risk_level") == "high":
            return "denied"
        if spec.get("requires_confirmation"):
            return "approved"
        return "not_required"

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _token_ok(self, device: DeviceInfo, device_token: str) -> bool:
        expected = (device.metadata or {}).get("device_token")
        return bool(device_token) and expected == device_token

    async def require_device_token(self, device_id: str, device_token: str) -> DeviceInfo:
        device = await self._registry.get(device_id)
        if device is None:
            raise PermissionError("device_not_found")
        if not self._token_ok(device, device_token):
            raise PermissionError("invalid_device_token")
        return device

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    async def _audit_row(
        self,
        *,
        user_id: str,
        device_id: str,
        command_id: Optional[str],
        command: str,
        actor: str,
        action: str,
        details: str = "",
    ) -> None:
        await self._audit.append(
            {
                "user_id": user_id,
                "device_id": device_id,
                "command_id": command_id,
                "command": command,
                "actor": actor,
                "action": action,
                "details": details,
            }
        )

    # ------------------------------------------------------------------
    # Registration / heartbeat
    # ------------------------------------------------------------------

    async def register_device(self, device: DeviceInfo) -> Tuple[DeviceInfo, str]:
        token = secrets.token_urlsafe(32)
        merged_meta = dict(device.metadata or {})
        merged_meta["device_token"] = token
        device = device.model_copy(update={"metadata": merged_meta, "last_heartbeat": _utcnow(), "is_online": True})
        registered = await self._registry.register(device)
        await self._audit_row(
            user_id=registered.user_id,
            device_id=registered.device_id,
            command_id=None,
            command="",
            actor="device",
            action="created",
            details="device_register",
        )
        return registered, token

    async def heartbeat(self, device_id: str, device_token: str, ip_address: Optional[str]) -> DeviceInfo:
        await self.require_device_token(device_id, device_token)
        device = await self._registry.heartbeat(device_id, ip_address)
        if device is None:
            raise LookupError("device_not_found")
        return device

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def send_command(
        self,
        *,
        user_id: str,
        command: str,
        payload: Dict[str, Any],
        device_id: Optional[str],
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """Returns (success, body_or_command_dict, http_detail_if_error)."""
        spec, err = self.validate_command(command, payload)
        if err == "unknown_command":
            return False, {}, f"Unknown command: {command}"
        if err == "payload_invalid":
            return False, {}, f"Payload validation failed for {command}"
        if err == "high_risk_blocked":
            await self._audit_row(
                user_id=user_id,
                device_id=device_id or "",
                command_id=None,
                command=command,
                actor="user",
                action="denied",
                details="high_risk_blocked",
            )
            return False, {"error": "high_risk_blocked", "reason": "此类指令已被网关拒绝。"}, None

        target, detail = await self._resolve_target_device(user_id, device_id)
        if target is None:
            return False, {}, detail or "No target device"

        if not target.is_online:
            return False, {}, "Device is offline"
        if command not in target.capabilities:
            return False, {}, "Device has not enabled this capability"

        ttl = int(self._settings.device_command_ttl_seconds)
        now = _utcnow()
        expires_at = now + timedelta(seconds=ttl)
        cmd_id = uuid.uuid4().hex
        confirmation_status = self.confirmation_for_user_request(spec)
        if confirmation_status == "denied":
            return False, {}, "Command denied"

        entry: Dict[str, Any] = {
            "command_id": cmd_id,
            "user_id": user_id,
            "device_id": target.device_id,
            "command": command,
            "payload": payload,
            "risk_level": spec["risk_level"],
            "requires_confirmation": bool(spec.get("requires_confirmation")),
            "confirmation_status": confirmation_status,
            "status": "pending",
            "created_at": _iso(now),
            "updated_at": _iso(now),
            "expires_at": _iso(expires_at),
            "delivered_at": None,
            "result": None,
            "error": None,
        }

        await self._commands.create(entry)
        await self._audit_row(
            user_id=user_id,
            device_id=target.device_id,
            command_id=cmd_id,
            command=command,
            actor="user",
            action="created",
            details="",
        )

        # Publish a claimable receipt before push: a fast client may respond
        # while delivery is still awaited. Never overwrite its newer state.
        delivered = await self._commands.transition(
            cmd_id,
            {"pending"},
            {
                "status": "delivered",
                "delivered_at": _iso(_utcnow()),
            },
        )
        if delivered is None:
            return False, {}, "Command no longer deliverable"
        await self._audit_row(
            user_id=user_id,
            device_id=target.device_id,
            command_id=cmd_id,
            command=command,
            actor="system",
            action="delivered",
        )
        ws_delivered = False
        try:
            from .api import get_ws_push

            ws_delivered = await get_ws_push()(target.device_id, {"type": "command", "command": dict(delivered)})
        except Exception:
            pass

        if not ws_delivered:
            try:
                await self._transport.subscribe(target.device_id)
                await self._transport.deliver(dict(delivered))
            except Exception as exc:
                logger.warning("gateway.transport_deliver_failed", command_id=cmd_id, reason=type(exc).__name__)
                failed = await self._commands.transition(
                    cmd_id,
                    {"delivered"},
                    {"status": "failed", "error": "transport_unavailable"},
                )
                if failed is None:
                    return True, dict(await self._commands.get(cmd_id) or delivered), None
                await self._audit_row(
                    user_id=user_id,
                    device_id=target.device_id,
                    command_id=cmd_id,
                    command=command,
                    actor="system",
                    action="failed",
                    details="transport_unavailable",
                )
                return False, {}, "Device transport is unavailable"
        logger.info("gateway.command_delivered", command_id=cmd_id, device_id=target.device_id)
        return True, dict(await self._commands.get(cmd_id) or delivered), None

    async def _resolve_target_device(
        self, user_id: str, device_id: Optional[str]
    ) -> Tuple[Optional[DeviceInfo], Optional[str]]:
        if device_id:
            target = await self._registry.get(device_id)
            if target is None:
                return None, "Device not found"
            if target.user_id != user_id:
                return None, "Device not found"
            return target, None

        online = await self._registry.list_for_user(user_id, online_only=True)
        online = [d for d in online if d.user_id == user_id]
        if len(online) == 0:
            return None, "No online devices available"
        if len(online) > 1:
            names = ", ".join(d.device_name for d in online)
            return None, f"Multiple devices online ({names}). Please specify a device_id."
        return online[0], None

    async def cancel_command(self, *, user_id: str, command_id: str) -> Dict[str, Any]:
        row = await self._commands.get(command_id)
        if row is None:
            raise LookupError("not_found")
        if row["user_id"] != user_id:
            raise PermissionError("forbidden")
        st = row["status"]
        if st in _TERMINAL_STATUSES:
            raise ValueError("already_terminal")
        updated = await self._commands.transition(
            command_id,
            set(_ACTIVE_STATUSES),
            {"status": "cancelled", "error": "cancelled_by_user"},
        )
        if updated is None:
            raise ValueError("already_terminal")
        await self._audit_row(
            user_id=user_id,
            device_id=row["device_id"],
            command_id=command_id,
            command=row.get("command", ""),
            actor="user",
            action="cancelled",
            details="",
        )
        return dict(updated or row)

    async def claim_next(self, *, device_id: str, device_token: str) -> Optional[Dict[str, Any]]:
        device = await self.require_device_token(device_id, device_token)
        row = await self._commands.find_next_delivered(device_id)
        if row is None:
            return None
        if row["user_id"] != device.user_id:
            raise PermissionError("forbidden")
        if self._is_expired(row):
            await self._timeout_command(row, "expired_before_claim")
            return None
        updated = await self._commands.transition(row["command_id"], {"delivered"}, {"status": "claimed"})
        if updated is None:
            return None
        await self._audit_row(
            user_id=row["user_id"],
            device_id=device_id,
            command_id=row["command_id"],
            command=row.get("command", ""),
            actor="device",
            action="claimed",
            details="",
        )
        return dict(updated or row)

    async def claim_command(self, *, command_id: str, device_id: str, device_token: str) -> Dict[str, Any]:
        await self.require_device_token(device_id, device_token)
        row = await self._commands.get(command_id)
        if row is None:
            raise LookupError("not_found")
        if row["device_id"] != device_id:
            raise PermissionError("forbidden")
        if row["status"] != "delivered":
            raise ValueError("invalid_state")
        if self._is_expired(row):
            await self._timeout_command(row, "expired_before_claim")
            raise ValueError("expired")
        updated = await self._commands.transition(command_id, {"delivered"}, {"status": "claimed"})
        if updated is None:
            raise ValueError("invalid_state")
        await self._audit_row(
            user_id=row["user_id"],
            device_id=device_id,
            command_id=command_id,
            command=row.get("command", ""),
            actor="device",
            action="claimed",
            details="explicit_claim",
        )
        return dict(updated or row)

    async def mark_running(self, *, command_id: str, device_id: str, device_token: str) -> Dict[str, Any]:
        await self.require_device_token(device_id, device_token)
        row = await self._commands.get(command_id)
        if row is None:
            raise LookupError("not_found")
        if row["device_id"] != device_id:
            raise PermissionError("forbidden")
        if row["status"] != "claimed":
            raise ValueError("invalid_state")
        if self._is_expired(row):
            await self._timeout_command(row, "expired")
            raise ValueError("expired")
        updated = await self._commands.transition(command_id, {"claimed"}, {"status": "running"})
        if updated is None:
            raise ValueError("invalid_state")
        await self._audit_row(
            user_id=row["user_id"],
            device_id=device_id,
            command_id=command_id,
            command=row.get("command", ""),
            actor="device",
            action="running",
            details="mark_running",
        )
        return dict(updated or row)

    def _is_expired(self, row: Dict[str, Any]) -> bool:
        raw = row.get("expires_at")
        if not raw:
            return False
        try:
            exp = datetime.fromisoformat(str(raw))
        except ValueError:
            return False
        return _utcnow() > exp.replace(tzinfo=None) if exp.tzinfo else _utcnow() > exp

    async def _timeout_command(self, row: Dict[str, Any], details: str) -> None:
        from shared_runtime.user_lifecycle import user_operation

        async with user_operation(row["user_id"]):
            cid = row["command_id"]
            updated = await self._commands.transition(
                cid, set(_ACTIVE_STATUSES), {"status": "timeout", "error": details}
            )
            if updated is None:
                return
            await self._audit_row(
                user_id=row["user_id"],
                device_id=row["device_id"],
                command_id=cid,
                command=row.get("command", ""),
                actor="system",
                action="timeout",
                details=details,
            )

    async def apply_command_result(
        self,
        *,
        command_id: str,
        device_id: str,
        device_token: str,
        status: str,
        result: Optional[Dict[str, Any]],
        error: Optional[str],
    ) -> Dict[str, Any]:
        await self.require_device_token(device_id, device_token)
        row = await self._commands.get(command_id)
        if row is None:
            raise LookupError("not_found")
        if row["device_id"] != device_id:
            raise PermissionError("forbidden")

        valid = {"succeeded", "failed", "denied", "timeout"}
        if status not in valid:
            raise ValueError("bad_status")

        if row["status"] in _TERMINAL_STATUSES:
            # Idempotent: return stored row unchanged
            return dict(row)

        if row["status"] not in {"claimed", "running"}:
            raise ValueError("invalid_state")

        updated = await self._commands.transition(
            command_id,
            {"claimed", "running"},
            {"status": status, "result": result, "error": error},
        )
        if updated is None:
            return dict(await self._commands.get(command_id) or row)
        await self._audit_row(
            user_id=row["user_id"],
            device_id=device_id,
            command_id=command_id,
            command=row.get("command", ""),
            actor="device",
            action=status,
            details=error or "",
        )
        return dict(updated or row)

    async def get_command_for_user(self, *, command_id: str, user_id: Optional[str]) -> Dict[str, Any]:
        row = await self._commands.get(command_id)
        if row is None:
            raise LookupError("not_found")
        if user_id is not None and row["user_id"] != user_id:
            raise PermissionError("forbidden")
        return dict(row)

    async def list_commands_user(self, *, user_id: str, device_id: Optional[str]) -> List[Dict[str, Any]]:
        rows = await self._commands.list_for_user(user_id, limit=100)
        if device_id:
            rows = [r for r in rows if r["device_id"] == device_id]
        return rows[:50]

    async def list_audit(self, *, user_id: Optional[str], device_id: Optional[str]) -> List[Dict[str, Any]]:
        return await self._audit.list_for_scope(user_id=user_id, device_id=device_id, limit=100)

    async def scan_timeouts(self) -> int:
        """Mark expired non-terminal commands as timeout. Returns number updated."""
        rows = await self._commands.list_non_terminal()
        n = 0
        for row in rows:
            if row["status"] not in _ACTIVE_STATUSES:
                continue
            if not self._is_expired(row):
                continue
            import asyncio

            from shared_runtime.user_lifecycle import StaleUserOperation

            try:
                await asyncio.create_task(self._timeout_command(row, "ttl_expired"))
            except StaleUserOperation:
                continue
            n += 1
        return n

    def transport_health(self) -> Dict[str, Any]:
        return self._transport.health()
