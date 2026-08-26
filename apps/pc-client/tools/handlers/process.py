"""Process management."""

import json
import subprocess
import sys
from typing import Any, Dict

from registry import ToolResult, get_registry


def register_process_handlers() -> None:
    reg = get_registry()

    @reg.register("list_processes", "List running processes", risk="low")
    def list_processes(_params: Dict[str, Any]) -> ToolResult:
        try:
            if sys.platform == "win32":
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Get-Process | Select-Object -First 50 Id, ProcessName, CPU, WorkingSet64 | ConvertTo-Json"],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                procs = json.loads(r.stdout) if r.stdout else []
                if isinstance(procs, dict):
                    procs = [procs]
                return ToolResult(ok=True, message=f"Found {len(procs)} processes", data={"processes": procs})
            else:
                r = subprocess.run(["ps", "aux", "--no-headers"], capture_output=True, text=True)
                lines = r.stdout.strip().split("\n")[:50]
                return ToolResult(ok=True, message=f"Found {len(lines)} processes", data={"processes": lines})
        except Exception as exc:
            return ToolResult(ok=False, message=str(exc))

    @reg.register("launch_app", "Launch an application by name or path", risk="medium", requires_confirm=True)
    def launch_app(params: Dict[str, Any]) -> ToolResult:
        app = params.get("app", "").strip()
        if not app:
            return ToolResult(ok=False, message="No application specified")
        try:
            if sys.platform == "win32":
                subprocess.Popen(["start", "", app], shell=True)
            else:
                subprocess.Popen([app])
            return ToolResult(ok=True, message=f"Launched {app}")
        except Exception as exc:
            return ToolResult(ok=False, message=str(exc))


register_process_handlers()
