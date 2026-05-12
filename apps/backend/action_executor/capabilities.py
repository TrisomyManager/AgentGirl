"""User-facing capabilities catalogue.

Translates BUILTIN_ACTIONS / action2d metadata into a product-shaped
capability list: user-visible title, grouping, example triggers, and
live availability status. Never exposes cold internal concepts like
"handler" / "registry" / "params_schema" to the end user.

This module is imported at route-resolution time (not startup), so it's
safe to call get_runtime_voice_config / get_runtime_llm_config etc.
"""

from __future__ import annotations

import os
from typing import Any

from action_executor.handlers import BUILTIN_ACTIONS

# ---------------------------------------------------------------------------
# User-facing capability definitions
# ---------------------------------------------------------------------------

_USER_CAPABILITIES: list[dict[str, Any]] = [
    {
        "id": "reminder",
        "title": "提醒我",
        "group": "生活助手",
        "description": "帮你在指定时间提醒一件事。支持重复提醒。",
        "examples": [
            "明天上午10点提醒我交材料",
            "30分钟后提醒我喝水",
            "每天晚上10点提醒我早点休息",
        ],
        "action_names": ["set_reminder", "list_reminders", "cancel_reminder", "timer_countdown"],
    },
    {
        "id": "weather",
        "title": "查天气",
        "group": "查询能力",
        "description": "帮你查询某地天气和出行提醒。",
        "examples": [
            "帮我看看明天上海会不会下雨",
            "今天北京多少度",
        ],
        "action_names": ["get_weather"],
    },
    {
        "id": "time",
        "title": "看时间",
        "group": "查询能力",
        "description": "告诉你现在的时间和星期几。",
        "examples": [
            "现在几点了？",
            "今天几号？",
        ],
        "action_names": ["get_time"],
    },
    {
        "id": "memory_storage",
        "title": "记住这件事",
        "group": "记忆与关系",
        "description": "把对你重要的信息记下来。",
        "examples": [
            "记住我不喜欢太甜的奶茶",
        ],
        "action_names": ["update_user_profile"],
    },
    {
        "id": "memory_recall",
        "title": "回忆一下",
        "group": "记忆与关系",
        "description": "从我们的记忆里找相关内容。",
        "examples": [
            "我之前说过最近在忙什么？",
            "你还记得我的名字吗？",
        ],
        "action_names": ["query_memory"],
    },
    {
        "id": "web_search",
        "title": "帮我搜一下",
        "group": "查询能力",
        "description": "搜索网络获取最新信息。",
        "examples": [
            "帮我搜一下今天的热搜",
            "查一下Python 3.12的新特性",
        ],
        "action_names": ["web_search"],
        "requires_config": True,
    },
    {
        "id": "action_animation",
        "title": "做个动作",
        "group": "设备与动作",
        "description": "让小暖配合情绪做动作或表情。",
        "examples": [
            "小暖，开心地挥挥手",
        ],
        "action_names": [],
    },
    {
        "id": "device_list",
        "title": "查看设备",
        "group": "设备与动作",
        "description": "查看你绑定的设备在线状态和能力。",
        "examples": [
            "我的电脑在线吗？",
            "我有几台设备？",
        ],
        "action_names": ["list_devices"],
    },
    {
        "id": "device_notify",
        "title": "设备通知",
        "group": "设备与动作",
        "description": "给你的设备发送通知提醒。",
        "examples": [
            "给我的电脑发个提醒",
            "让电脑提醒我喝水",
        ],
        "action_names": ["device_notify"],
    },
    {
        "id": "device_actions",
        "title": "操作设备",
        "group": "设备与动作",
        "description": "让设备执行操作（打开网页、Ping 测试等）。",
        "examples": [
            "让电脑打开百度",
            "帮我ping一下电脑",
        ],
        "action_names": ["device_ping", "device_open_url"],
    },
]

# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------


def _is_lite_mode() -> bool:
    return os.environ.get("COMPANION_LITE_MODE", "").strip().lower() in ("1", "true", "yes")


def _capability_status(cap: dict[str, Any]) -> str:
    """Compute a user-facing status for this capability.

    Returns one of: ready | degraded | needs_config | disabled | experimental
    """
    action_names: list[str] = cap.get("action_names", [])
    if not action_names:
        return "experimental"

    registered = _get_registered_names()
    active = set(action_names) & registered

    if not active:
        return "disabled"

    if cap.get("requires_config"):
        if cap["id"] == "web_search":
            from shared_runtime.config import get_settings
            settings = get_settings()
            key = getattr(settings, "search_api_key", None)
            return "ready" if key else "needs_config"

    # Check if any underlying action needs a key that isn't set
    reg = _get_registry()
    for a_name in active:
        act = reg._actions.get(a_name) if reg else None
        if act and act.needs_api_key and act.api_key_env_var:
            env_var = act.api_key_env_var
            if not os.environ.get(env_var):
                return "needs_config"

    return "ready"


def _missing_config_for(cap: dict[str, Any]) -> list[str]:
    """Return a list of missing env-var config keys for this capability."""
    missing: list[str] = []
    if cap.get("requires_config") and cap["id"] == "web_search":
        from shared_runtime.config import get_settings
        settings = get_settings()
        if not getattr(settings, "search_api_key", None):
            missing.append("COMPANION_SEARCH_API_KEY")
    reg = _get_registry()
    for a_name in cap.get("action_names", []):
        act = reg._actions.get(a_name) if reg else None
        if act and act.needs_api_key and act.api_key_env_var:
            if not os.environ.get(act.api_key_env_var):
                missing.append(act.api_key_env_var)
    return missing


def _get_registry():
    from action_executor.registry import get_registry as gr
    return gr()


def _get_registered_names() -> set[str]:
    reg = _get_registry()
    return set(reg._actions.keys())


def build_capabilities() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for cap in _USER_CAPABILITIES:
        action_names = cap.get("action_names", [])
        registered = _get_registered_names()
        active = set(action_names) & registered
        status = _capability_status(cap)
        result.append({
            "id": cap["id"],
            "title": cap["title"],
            "group": cap["group"],
            "description": cap.get("description", ""),
            "examples": list(cap.get("examples", [])),
            "enabled": bool(active),
            "status": status,
            "requires_config": bool(cap.get("requires_config")),
            "missing_config": _missing_config_for(cap),
            "lite_mode_supported": _is_lite_mode(),
        })
    return result
