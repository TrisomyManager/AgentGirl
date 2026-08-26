#!/usr/bin/env python3
"""Local HTTP tool server for 小暖 PC Client.

Electron main process spawns this server to expose system capabilities
through a simple HTTP API. All handlers auto-register via imports.
"""

from __future__ import annotations

import argparse
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

from handlers import system as _system  # noqa: F401
from handlers import browser as _browser  # noqa: F401
from handlers import filesystem as _filesystem  # noqa: F401
from handlers import clipboard as _clipboard  # noqa: F401
from handlers import process as _process  # noqa: F401
from handlers import screenshot as _screenshot  # noqa: F401

from registry import get_registry


class ToolHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "service": "xiaonuan-tool-server"})
        elif self.path == "/tools/list":
            reg = get_registry()
            self._send_json(200, {"tools": reg.list_tools()})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/tools/exec":
            length = int(self.headers.get("Content-Length", 0))
            body_raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(body_raw)
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid json"})
                return

            name = body.get("name", "").strip()
            params = body.get("params", {})
            if not name:
                self._send_json(400, {"error": "missing tool name"})
                return

            reg = get_registry()
            result = reg.exec(name, params)
            self._send_json(200, {"ok": result.ok, "message": result.message, "data": result.data})
        else:
            self._send_json(404, {"error": "not found"})


def main():
    parser = argparse.ArgumentParser(description="小暖 Local Tool Server")
    parser.add_argument("--port", type=int, default=18721, help="Listen port")
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), ToolHandler)
    print(f"tool_server ready on 127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
