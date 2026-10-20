"""System info, volume control, notifications."""

import platform
import json
import subprocess
import sys
from typing import Any, Dict

from registry import ToolResult, get_registry


def _win_notify(title: str, body: str) -> None:
    ps = (
        "$ErrorActionPreference='Stop'; [Console]::InputEncoding=[Text.UTF8Encoding]::new();"
        "$p=[Console]::In.ReadToEnd() | ConvertFrom-Json;"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
        "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        '$t.GetElementsByTagName("text")[0].AppendChild($t.CreateTextNode([string]$p.title)) > $null;'
        '$t.GetElementsByTagName("text")[1].AppendChild($t.CreateTextNode([string]$p.body)) > $null;'
        "$n = New-Object Windows.UI.Notifications.ToastNotification($t);"
        '[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("小暖").Show($n)'
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        input=json.dumps({"title": title, "body": body}, ensure_ascii=False).encode(
            "utf-8"
        ),
        timeout=10,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def register_system_handlers() -> None:
    reg = get_registry()

    @reg.register("system_info", "Get system info (OS, CPU, memory, disk)", risk="low")
    def system_info(_params: Dict[str, Any]) -> ToolResult:
        uname = platform.uname()
        return ToolResult(
            ok=True,
            message="System info retrieved",
            data={
                "platform": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": uname.machine,
                "processor": uname.processor,
            },
        )

    @reg.register("show_notification", "Show a Windows toast notification", risk="low")
    def show_notification(params: Dict[str, Any]) -> ToolResult:
        title = params.get("title", "小暖")
        body = params.get("body", params.get("text", ""))
        if not body:
            return ToolResult(ok=False, message="Missing notification body")
        if platform.system() == "Windows":
            _win_notify(title, body)
        else:
            subprocess.run(["notify-send", "--", title, body], timeout=10, check=True)
        return ToolResult(ok=True, message="Notification shown")

    @reg.register(
        "volume_control", "Adjust system volume", risk="medium", requires_confirm=True
    )
    def volume_control(params: Dict[str, Any]) -> ToolResult:
        return ToolResult(ok=False, message="音量控制尚未实现。")

    @reg.register("get_device_status", "Get current device status", risk="low")
    def get_device_status(_params: Dict[str, Any]) -> ToolResult:
        return ToolResult(
            ok=True,
            message="Device status",
            data={
                "platform": platform.system(),
                "hostname": platform.node(),
                "python_version": sys.version,
            },
        )


register_system_handlers()
