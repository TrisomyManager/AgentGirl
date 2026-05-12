"""Smoke-test the user-facing Lite chat flow end-to-end."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_URL = "http://127.0.0.1:8000"


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    env["COMPANION_LITE_MODE"] = "true"
    env.setdefault("COMPANION_ENABLE_VOICE", "false")
    env.setdefault("COMPANION_ENABLE_ACTION_2D", "false")
    env.setdefault("COMPANION_ENABLE_DEVICE_COORDINATION", "false")
    env.setdefault("COMPANION_ENABLE_MEMORY_PIPELINE", "true")
    return env


def _wait_until_ready(timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{SERVER_URL}/health", timeout=2.0)
            if resp.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Lite server did not become healthy in time.")


def _send_turn(client: httpx.Client, session_id: str, message: str) -> dict:
    payload = {
        "session_id": session_id,
        "user": {
            "user_id": "smoke-user",
            "display_name": "Smoke Tester",
        },
        "user_message": message,
        "platform": "app",
    }
    resp = client.post(f"{SERVER_URL}/orchestrator/turn", json=payload, timeout=20.0)
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    env = _build_env()
    process = subprocess.Popen(
        [sys.executable, "scripts/start_lite_server.py"],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _wait_until_ready()
        session_id = f"smoke-session-{int(time.time())}"
        with httpx.Client() as client:
            first = _send_turn(client, session_id, "我叫小王，我喜欢咖啡。")
            second = _send_turn(client, session_id, "你还记得我喜欢什么吗？")

        print("First reply:", first.get("assistant_message", ""))
        print("Second reply:", second.get("assistant_message", ""))

        reply_text = second.get("assistant_message", "")
        if "咖啡" not in reply_text and "小王" not in reply_text:
            raise RuntimeError("Memory recall reply did not mention the first turn details.")

        print("Smoke test passed.")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
