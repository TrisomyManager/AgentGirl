"""Screen capture — high risk, requires confirmation."""

import platform
import subprocess
import tempfile
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from registry import ToolResult, get_registry
from policy import get_policy


def _now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def register_screenshot_handlers() -> None:
    reg = get_registry()

    @reg.register(
        "screenshot", "Capture the current screen", risk="high", requires_confirm=True
    )
    def screenshot(_params: Dict[str, Any]) -> ToolResult:
        try:
            descriptor, filename = tempfile.mkstemp(
                prefix="capture-", suffix=".png", dir=get_policy().root
            )
            os.close(descriptor)
            path = Path(filename)

            if platform.system() == "Windows":
                from PIL import ImageGrab

                img = ImageGrab.grab()
                img.save(str(path), "PNG")
            elif platform.system() == "Darwin":
                subprocess.run(
                    ["screencapture", "-x", str(path)], check=True, timeout=10
                )
            else:
                subprocess.run(
                    ["import", "-window", "root", str(path)], check=True, timeout=10
                )

            return ToolResult(
                ok=True,
                message="Screenshot captured",
                data={"path": path.name, "size": path.stat().st_size},
            )
        except ImportError:
            return ToolResult(
                ok=False, message="Pillow not installed. Run: pip install Pillow"
            )
        except Exception as exc:
            return ToolResult(ok=False, message=str(exc))


register_screenshot_handlers()
