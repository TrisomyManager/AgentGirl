"""Task dispatcher — route tasks to appropriate devices based on capability matching."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from shared.models import DeviceInfo

from .registry import DeviceRegistry

logger = structlog.get_logger(__name__)

# Simple capability mapping for common task types
_TASK_CAPABILITY_MAP: Dict[str, List[str]] = {
    "voice_output": ["speaker", "audio_playback", "voice"],
    "display": ["screen", "display", "visual"],
    "action": ["actuator", "motor", "action"],
    "notification": ["push", "notification", "screen"],
    "camera": ["camera", "video_capture"],
    "microphone": ["microphone", "audio_capture", "voice_input"],
}


class TaskDispatcher:
    """Routes tasks to the best available device for a user."""

    def __init__(self, registry: DeviceRegistry) -> None:
        self._registry = registry

    async def dispatch(
        self,
        user_id: str,
        task_type: str,
        payload: Dict[str, Any],
        preferred_device_id: Optional[str] = None,
    ) -> Optional[DeviceInfo]:
        """Select the best device and return it (caller then sends command via MQTT).

        Returns the selected DeviceInfo, or None if no suitable device found.
        """
        # 1. Preferred device explicit override
        if preferred_device_id:
            device = await self._registry.get(preferred_device_id)
            if device and device.is_online and device.user_id == user_id:
                logger.info(
                    "task_dispatcher.preferred",
                    user_id=user_id,
                    task_type=task_type,
                    device_id=device.device_id,
                )
                return device
            logger.warning(
                "task_dispatcher.preferred_unavailable",
                user_id=user_id,
                preferred_device_id=preferred_device_id,
            )

        # 2. Capability-based routing
        required_caps = _TASK_CAPABILITY_MAP.get(task_type, [task_type])
        device = await self._registry.find_best_for_task(user_id, required_caps)
        if device:
            logger.info(
                "task_dispatcher.routed",
                user_id=user_id,
                task_type=task_type,
                device_id=device.device_id,
                capabilities=device.capabilities,
            )
            return device

        # 3. Fallback: any online device for user
        devices = await self._registry.list_for_user(user_id, online_only=True)
        if devices:
            fallback = devices[0]
            logger.info(
                "task_dispatcher.fallback",
                user_id=user_id,
                task_type=task_type,
                device_id=fallback.device_id,
            )
            return fallback

        logger.warning("task_dispatcher.no_device", user_id=user_id, task_type=task_type)
        return None

    async def broadcast(
        self,
        user_id: str,
        task_type: str,
        payload: Dict[str, Any],
    ) -> List[DeviceInfo]:
        """Return all suitable online devices for broadcasting."""
        required_caps = _TASK_CAPABILITY_MAP.get(task_type, [task_type])
        candidates = await self._registry.find_by_capability(user_id, required_caps[0])
        # Ensure at least one capability matches
        suitable: List[DeviceInfo] = []
        for d in candidates:
            if any(cap in d.capabilities for cap in required_caps):
                suitable.append(d)
        if not suitable:
            suitable = await self._registry.list_for_user(user_id, online_only=True)
        logger.info(
            "task_dispatcher.broadcast",
            user_id=user_id,
            task_type=task_type,
            device_count=len(suitable),
        )
        return suitable
