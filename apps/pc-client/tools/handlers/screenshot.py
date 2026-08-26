"""Screen capture — high risk, requires confirmation."""

import platform
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from registry import ToolResult, get_registry


def _now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def register_screenshot_handlers() -> None:
    reg = get_registry()

    @reg.register("screenshot", "Capture the current screen", risk="high", requires_confirm=True)
    def screenshot(_params: Dict[str, Any]) -> ToolResult:
        try:
            path = Path(tempfile.gettempdir()) / f"xiaonuan_screenshot_{_now()}.png"

            if platform.system() == "Windows":
                from PIL import ImageGrab
                img = ImageGrab.grab()
                img.save(str(path), "PNG")
            elif platform.system() == "Darwin":
                subprocess.run(["screencapture", "-x", str(path)], check=True)
            else:
                subprocess.run(["import", "-window", "root", str(path)], check=True)

            return ToolResult(
                ok=True,
                message="Screenshot captured",
                data={"path": str(path), "size": path.stat().st_size},
            )
        except ImportError:
            return ToolResult(ok=False, message="Pillow not installed. Run: pip install Pillow")
        except Exception as exc:
            return ToolResult(ok=False, message=str(exc))


register_screenshot_handlers()
