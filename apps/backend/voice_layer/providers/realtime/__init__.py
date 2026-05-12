"""Realtime voice provider registry.

Supports hot-switchable providers via configuration. Each provider
implements ``RealtimeVoiceProvider`` from ``shared_contracts.protocols``.

Available providers:
    - local: Wraps local ASR (faster-whisper) + LLM + local TTS (Piper)
    - cloud: Cloud ASR + LLM + Cloud TTS (SiliconFlow / OpenAI / DashScope)
    - volc_realtime: Volcengine end-to-end realtime voice API
"""

from __future__ import annotations

from shared_contracts.protocols import RealtimeVoiceProvider

_providers: dict[str, RealtimeVoiceProvider] = {}
_default_provider_name: str = "local"
_fallback_reason: str | None = None
_configured_provider: str = "local"

_CLOUD_TTS_PROVIDERS = {"siliconflow", "openai", "dashscope", "fish_audio", "xiaomi_mimo"}


def reset_realtime_registry() -> None:
    """Clear provider registry (for test isolation)."""
    global _providers, _default_provider_name, _fallback_reason, _configured_provider
    _providers = {}
    _default_provider_name = "local"
    _fallback_reason = None
    _configured_provider = "local"


def register_provider(name: str, provider: RealtimeVoiceProvider) -> None:
    _providers[name] = provider


def get_provider(name: str | None = None) -> RealtimeVoiceProvider:
    key = name or _default_provider_name
    if key in _providers:
        return _providers[key]
    return _providers[_default_provider_name]


def set_default_provider(name: str) -> None:
    global _default_provider_name
    _default_provider_name = name


def list_providers() -> list[str]:
    return list(_providers.keys())


def init_registry() -> None:
    """Lazy-import and register all known providers.

    Called once during voice_layer startup.
    """
    global _default_provider_name, _fallback_reason, _configured_provider
    import structlog

    from shared_runtime.config import get_settings
    from voice_layer.providers.realtime.local_realtime import LocalRealtimeProvider

    register_provider("local", LocalRealtimeProvider())

    settings = get_settings()
    configured = settings.realtime_voice_provider
    _configured_provider = configured
    _fallback_reason = None

    if configured == "volc_realtime":
        if settings.volc_app_id and settings.volc_access_token:
            from voice_layer.providers.realtime.volc_realtime import VolcRealtimeProvider

            register_provider("volc_realtime", VolcRealtimeProvider())
            _default_provider_name = "volc_realtime"
        else:
            _fallback_reason = "missing_credentials"
            structlog.get_logger("voice_layer.providers.realtime").warning(
                "volc_realtime.requested_but_missing_credentials",
                fallback="local",
            )
        return

    from voice_layer.providers.realtime.cloud_realtime import CloudRealtimeProvider
    register_provider("cloud", CloudRealtimeProvider())

    _cloud_ok = _can_use_cloud()
    if configured == "cloud":
        if not _cloud_ok:
            _fallback_reason = "missing_voice_credentials"
            structlog.get_logger("voice_layer.providers.realtime").warning(
                "cloud_realtime.requested_but_missing_voice_credentials",
                note="仍使用云端管线；请在设置页补全 ASR/TTS，连接将报错直至配置完整",
            )
        _default_provider_name = "cloud"
    elif configured == "local":
        _default_provider_name = "local"
    else:
        # 默认走云端统一配置（设置页 ASR/TTS），避免在未显式选择 local 时落到 Piper/Whisper 本机实现
        if not _cloud_ok:
            _fallback_reason = "missing_voice_credentials"
        _default_provider_name = "cloud"


def _can_use_cloud() -> bool:
    """Check whether cloud realtime can be activated.

    Returns True when the runtime voice config contains both TTS and ASR
    API keys and the TTS provider is one of the supported cloud providers.
    """
    from shared_runtime.voice_runtime_config import get_runtime_voice_config

    rt = get_runtime_voice_config()
    tts_key = rt.get("tts_api_key") or ""
    asr_key = rt.get("asr_api_key") or ""
    tts_provider = (rt.get("tts_provider") or "").strip().lower()
    return bool(tts_key and asr_key and tts_provider in _CLOUD_TTS_PROVIDERS)


def is_registry_initialized() -> bool:
    return len(_providers) > 0


def get_realtime_status() -> dict:
    """Return a read-only snapshot of the realtime provider status.

    Returns a dict with:
        current_provider:  the provider currently serving requests.
        configured_provider:  the value of ``COMPANION_REALTIME_VOICE_PROVIDER``.
        fallback_reason:  str explanation if config was ignored, else None.

    This is a pure function — it does not open network endpoints.
    """
    return {
        "current_provider": _default_provider_name,
        "configured_provider": _configured_provider,
        "fallback_reason": _fallback_reason,
    }


__all__ = [
    "register_provider",
    "get_provider",
    "set_default_provider",
    "list_providers",
    "init_registry",
    "is_registry_initialized",
    "get_realtime_status",
    "reset_realtime_registry",
]
