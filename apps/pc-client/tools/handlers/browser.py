"""Browser / URL opening."""

import webbrowser
from typing import Any, Dict
from urllib.parse import urlparse

from registry import ToolResult, get_registry


def register_browser_handlers() -> None:
    reg = get_registry()

    @reg.register("open_url", "Open a URL in the default browser", risk="medium", requires_confirm=True)
    def open_url(params: Dict[str, Any]) -> ToolResult:
        url = params.get("url", "").strip()
        if not url:
            return ToolResult(ok=False, message="No URL provided")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ToolResult(ok=False, message=f"Unsupported URL scheme: {parsed.scheme}")
        webbrowser.open(url)
        return ToolResult(ok=True, message=f"Opened {url}")


register_browser_handlers()
