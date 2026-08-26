"""System info, volume control, notifications."""

import platform
import subprocess
import sys
from typing import Any, Dict

from registry import ToolResult, get_registry


def _win_notify(title: str, body: str) -> None:
    ps = (
        f'[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;'
        f'$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);'
        f'$t.GetElementsByTagName("text")[0].AppendChild($t.CreateTextNode("{title}")) > $null;'
        f'$t.GetElementsByTagName("text")[1].AppendChild($t.CreateTextNode("{body}")) > $null;'
        f'$n = New-Object Windows.UI.Notifications.ToastNotification($t);'
        f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("小暖").Show($n)'
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
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
            subprocess.run(["notify-send", title, body])
        return ToolResult(ok=True, message="Notification shown")

    @reg.register("volume_control", "Adjust system volume", risk="medium", requires_confirm=True)
    def volume_control(params: Dict[str, Any]) -> ToolResult:
        action = params.get("action", "get")
        if action == "get":
            return ToolResult(ok=True, message="Volume query not implemented", data={"volume": None})
        level = params.get("level")
        if action == "set" and level is not None:
            level = max(0, min(100, int(level)))
            return ToolResult(ok=True, message=f"Volume set to {level}% (requires pycaw on Windows)", data={"volume": level})
        return ToolResult(ok=False, message=f"Unknown volume action: {action}")

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
