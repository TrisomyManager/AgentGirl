"""Clipboard read/write."""

import subprocess
import sys
from typing import Any, Dict

from registry import ToolResult, get_registry


def _win_clipboard_read() -> str:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    return r.stdout if r.returncode == 0 else ""


def _win_clipboard_write(text: str) -> bool:
    safe = text.replace('"', '`"').replace("$", "`$")
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f'Set-Clipboard -Value "{safe}"'],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    return r.returncode == 0


def register_clipboard_handlers() -> None:
    reg = get_registry()

    @reg.register("clipboard_read", "Read text from clipboard", risk="medium")
    def clipboard_read(_params: Dict[str, Any]) -> ToolResult:
        try:
            text = _win_clipboard_read()
            return ToolResult(ok=True, message="Clipboard read", data={"text": text})
        except Exception as exc:
            return ToolResult(ok=False, message=str(exc))

    @reg.register("clipboard_write", "Write text to clipboard", risk="medium", requires_confirm=True)
    def clipboard_write(params: Dict[str, Any]) -> ToolResult:
        text = params.get("text", "")
        if not text:
            return ToolResult(ok=False, message="No text provided")
        try:
            _win_clipboard_write(text)
            return ToolResult(ok=True, message="Copied to clipboard")
        except Exception as exc:
            return ToolResult(ok=False, message=str(exc))


register_clipboard_handlers()
