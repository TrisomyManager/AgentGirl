"""Smoke-test a single /orchestrator/turn call in Lite Mode without a real LLM key.

Verifies:
- assistant_message is non-empty
- emotion_state.primary is a valid EmotionTag

Uses the rule-based reply path (_rule_based_reply) when no LLM provider is configured.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_URL = "http://127.0.0.1:8000"

VALID_EMOTION_TAGS = frozenset({
    "neutral", "happy", "sad", "angry", "surprised",
    "fearful", "disgusted", "affectionate", "concerned",
    "excited", "calm",
})


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    env["COMPANION_LITE_MODE"] = "true"
    env.setdefault("COMPANION_ENABLE_VOICE", "false")
    env.setdefault("COMPANION_ENABLE_ACTION_2D", "false")
    env.setdefault("COMPANION_ENABLE_DEVICE_COORDINATION", "false")
    env.setdefault("COMPANION_ENABLE_MEMORY_PIPELINE", "true")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COMPANION_OPENAI_API_KEY", "COMPANION_ANTHROPIC_API_KEY"):
        env.pop(key, None)
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

        with httpx.Client() as client:
            payload = {
                "session_id": "smoke-turn-session",
                "user": {
                    "user_id": "smoke-turn-user",
                    "display_name": "Smoke Tester",
                },
                "user_message": "你好呀，今天天气不错，我想和你聊聊天。",
                "platform": "app",
            }
            resp = client.post(f"{SERVER_URL}/orchestrator/turn", json=payload, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()

        assistant_message = data.get("assistant_message", "")
        if not assistant_message:
            raise RuntimeError("assistant_message is empty")

        emotion = data.get("emotion")
        if emotion is None:
            raise RuntimeError("emotion field is None, expected EmotionState dict")
        primary = emotion.get("primary")
        if primary not in VALID_EMOTION_TAGS:
            raise RuntimeError(f"emotion.primary={primary!r} is not a valid EmotionTag")

        print(f"assistant_message: {assistant_message}")
        print(f"emotion.primary: {primary}")
        print("Smoke test (lite turn) passed.")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
