#!/usr/bin/env python3
"""Private loopback bridge; its owning Electron process supplies an ephemeral key."""

import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from handlers import browser, clipboard, filesystem, process, screenshot, system  # noqa: F401
from policy import MAX_PAYLOAD_BYTES, get_policy
from registry import get_registry


class ToolHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        pass

    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(body) > 1024 * 1024:
            status, body = 413, b'{"ok":false,"message":"Result too large"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorize(self):
        hosts = {
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
        }
        token = self.headers.get("Authorization", "")
        if (
            self.headers.get("Host") not in hosts
            or self.headers.get("Origin") is not None
            or self.headers.get("Sec-Fetch-Site") is not None
            or self.headers.get("Sec-Fetch-Dest") is not None
            or not hmac.compare_digest(
                token.encode(), ("Bearer " + self.server.access_token).encode()
            )
        ):
            self._send_json(403, {"ok": False, "message": "本机工具访问被拒绝。"})
            return False
        return True

    def do_OPTIONS(self):
        self._send_json(403, {"ok": False})

    def do_GET(self):
        if not self._authorize():
            return
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        elif self.path == "/tools/list":
            self._send_json(200, {"tools": get_registry().list_tools()})
        else:
            self._send_json(404, {"ok": False})

    def do_POST(self):
        if not self._authorize():
            return
        if self.path != "/tools/exec":
            self._send_json(404, {"ok": False})
            return
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
                raise ValueError("Invalid framing")
            length = int(lengths[0])
            if (
                not 0 < length <= MAX_PAYLOAD_BYTES
                or self.headers.get_content_type() != "application/json"
            ):
                raise ValueError("Invalid payload")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete payload")

            def invalid_constant(value):
                raise ValueError("Non-finite JSON")

            body = json.loads(raw, parse_constant=invalid_constant)
            if not isinstance(body, dict) or set(body) - {"name", "params", "approved"}:
                raise ValueError("Invalid request")
            name = body.get("name")
            if not isinstance(name, str) or len(name) > 64:
                raise ValueError("Invalid name")
            result = get_registry().exec(
                name, body.get("params", {}), approved=body.get("approved") is True
            )
        except (ValueError, TypeError, RecursionError, UnicodeError, TimeoutError):
            self._send_json(400, {"ok": False, "message": "工具请求格式不正确。"})
            return
        self._send_json(
            200, {"ok": result.ok, "message": result.message, "data": result.data}
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    token = os.environ.pop("XIAONUAN_TOOL_TOKEN", "")
    if len(token) < 32 or not token.isascii():
        raise SystemExit("A private host token is required")
    get_policy()
    server = HTTPServer(("127.0.0.1", args.port), ToolHandler)
    server.access_token = token
    print(json.dumps({"type": "ready", "port": server.server_port}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
