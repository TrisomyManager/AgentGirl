"""HTTP/WebSocket stubs when ``COMPANION_ENABLE_VOICE`` is off (monolithic mode)."""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket
from fastapi.responses import JSONResponse

VOICE_DISABLED_DETAIL = (
    "语音模块未启用。请设置环境变量 COMPANION_ENABLE_VOICE=true 后重启，"
    "或运行: python scripts/start_lite_server.py --voice"
)

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe")
async def transcribe_disabled() -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": VOICE_DISABLED_DETAIL})


@router.post("/synthesize")
async def synthesize_disabled() -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": VOICE_DISABLED_DETAIL})


@router.get("/realtime/status")
async def realtime_status_disabled() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": VOICE_DISABLED_DETAIL,
            "current_provider": None,
            "configured_provider": None,
            "fallback_reason": "voice_module_disabled",
        },
    )


@router.websocket("/realtime")
async def realtime_ws_disabled(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_text(json.dumps({"type": "error", "msg": VOICE_DISABLED_DETAIL}, ensure_ascii=False))
    await websocket.close(code=1008)


@router.websocket("/stream")
async def stream_ws_disabled(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_text(json.dumps({"type": "error", "msg": VOICE_DISABLED_DETAIL}, ensure_ascii=False))
    await websocket.close(code=1008)
