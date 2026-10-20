"""Reference-host management metadata; no credentials or conversation content."""

from fastapi import APIRouter, Request

from shared_runtime.config import get_settings

router = APIRouter(prefix="/orchestrator/admin", tags=["administration"])


@router.get("/overview")
async def overview(request: Request):
    settings = get_settings()
    state = request.app.state
    platform_runtime = getattr(state, "platform_runtime", None)
    return {
        "ready": bool(getattr(state, "ready", False)),
        "modules": dict(getattr(state, "startup_modules", {})),
        "storage_mode": "sqlite" if settings.lite_mode else "postgresql",
        "access_mode": state.access_controller.mode,
        "coordination": "single_process",
        "platforms": platform_runtime.status() if platform_runtime else {"state": "disabled", "accounts": []},
    }
