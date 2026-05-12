"""Start companion-ai in Lite Mode for local testing on Windows."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["COMPANION_LITE_MODE"] = "true"

parser = argparse.ArgumentParser(description="Run companion-ai in Lite Mode (port 8000).")
parser.add_argument(
    "--voice",
    action="store_true",
    help="Enable voice routes (sets COMPANION_ENABLE_VOICE=true). Default is voice off for faster startup.",
)
args, _unknown = parser.parse_known_args()

if args.voice:
    os.environ["COMPANION_ENABLE_VOICE"] = "true"
else:
    os.environ.setdefault("COMPANION_ENABLE_VOICE", "false")

os.environ.setdefault("COMPANION_ENABLE_ACTION_2D", "false")
os.environ.setdefault("COMPANION_ENABLE_DEVICE_COORDINATION", "false")
os.environ.setdefault("COMPANION_ENABLE_MEMORY_PIPELINE", "true")

import uvicorn  # noqa: E402

from main import app  # noqa: E402

if __name__ == "__main__":
    if os.environ.get("COMPANION_ENABLE_VOICE", "").lower() not in ("1", "true", "yes", "on"):
        print(
            "[companion-ai] 语音模块未启用（默认）。"
            "需要 /voice/* 时请加上 --voice 或设置环境变量 COMPANION_ENABLE_VOICE=true。",
            file=sys.stderr,
        )
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, log_level="info")
