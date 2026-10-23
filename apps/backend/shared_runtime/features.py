"""Optional capabilities: one startup snapshot, dependency checks, atomic pending settings.

Inspired by dsh-pet's activation boundary. No upstream code or Qt dependencies.
Core services stay mandatory; optional service changes take effect on restart.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import RLock


@dataclass(frozen=True)
class Feature:
    name: str
    requires: tuple[str, ...] = ()


FEATURES = {
    "voice_layer": Feature("语音通话"),
    "action_layer": Feature("二维动作生成"),
    "proactive_care": Feature("主动关怀"),
    "desktop_context": Feature("桌面情境陪伴", ("proactive_care",)),
}
CORE = frozenset({
    "gateway_adapter", "core_orchestrator", "persona_engine", "memory_system",
    "action_executor", "device_coordination",
})


class FeatureManager:
    def __init__(self, path: Path, defaults: set[str] | None = None) -> None:
        self.path = path
        self._lock = RLock()
        enabled = self._load() if path.exists() else defaults or set()
        self._validate(enabled)
        self._pending = frozenset(enabled)
        self._active = self._pending

    def _load(self) -> list[str]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"无法读取功能配置：{self.path}；原文件已保留") from exc
        if (not isinstance(raw, dict) or type(raw.get("version")) is not int
                or raw.get("version") != 1 or not isinstance(raw.get("enabled"), list)):
            raise ValueError(f"不支持的功能配置：{self.path}；原文件已保留")
        return raw["enabled"]

    @staticmethod
    def _validate(enabled) -> None:
        if any(not isinstance(fid, str) or fid not in FEATURES for fid in enabled):
            raise ValueError("启用列表包含未知功能")
        for fid in enabled:
            missing = set(FEATURES[fid].requires) - set(enabled)
            if missing:
                raise ValueError(f"{FEATURES[fid].name}需要同时启用：{', '.join(sorted(missing))}")

    def is_active(self, feature_id: str) -> bool:
        return feature_id in CORE or feature_id in self._active

    def write_enabled(self, enabled: list[str]) -> None:
        self._validate(enabled)
        payload = {"version": 1, "enabled": sorted(set(enabled))}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, filename = tempfile.mkstemp(prefix=".features-", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, ensure_ascii=False, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(filename, self.path)
                self._pending = frozenset(enabled)
            finally:
                Path(filename).unlink(missing_ok=True)

    def status(self) -> dict:
        with self._lock:
            return {
                "active_enabled": sorted(self._active),
                "pending_enabled": sorted(self._pending),
                "restart_required": self._pending != self._active,
                "features": [
                    {"id": fid, "name": feature.name, "requires": list(feature.requires),
                     "active": fid in self._active, "enabled": fid in self._pending}
                    for fid, feature in FEATURES.items()
                ],
            }


@lru_cache(maxsize=1)
def get_feature_manager() -> FeatureManager:
    from shared_runtime.config import get_settings

    settings = get_settings()
    defaults = set()
    for fid, enabled in (("voice_layer", settings.enable_voice), ("action_layer", settings.enable_action_2d),
                         ("proactive_care", settings.proactive_enabled)):
        if enabled:
            defaults.add(fid)
    path = Path(os.environ.get("COMPANION_FEATURE_CONFIG_PATH") or
                Path(__file__).resolve().parent.parent / "companion_features.json")
    return FeatureManager(path, defaults=defaults)
