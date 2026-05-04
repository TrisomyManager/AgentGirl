"""Start companion-ai in Lite Mode for local testing on Windows."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["COMPANION_LITE_MODE"] = "true"
os.environ.setdefault("COMPANION_ENABLE_VOICE", "false")
os.environ.setdefault("COMPANION_ENABLE_ACTION_2D", "false")
os.environ.setdefault("COMPANION_ENABLE_DEVICE_COORDINATION", "false")
os.environ.setdefault("COMPANION_ENABLE_MEMORY_PIPELINE", "true")

import uvicorn

from main import app


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, log_level="info")
