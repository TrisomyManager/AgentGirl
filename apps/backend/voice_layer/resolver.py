"""VoiceProfile resolution — unified voice ID mapping across providers.

Ordinary TTS and realtime voice MUST use the same resolve_voice() path.
This ensures Azure, DashScope, Volc, and Piper voice IDs never leak across
modules.
"""

from __future__ import annotations

from shared_contracts.models import VoiceProfile


class UnknownProviderError(ValueError):
    """Raised when a provider is requested but has no mapping in the profile.

    This is always a configuration or integration bug — it should never be
    silently swallowed.
    """

    def __init__(self, provider_name: str, profile_id: str) -> None:
        super().__init__(
            f"Provider {provider_name!r} has no voice mapping in "
            f"voice profile {profile_id!r}. Check VoiceProfile.provider_voices."
        )
        self.provider_name = provider_name
        self.profile_id = profile_id


class VoiceProfileNotFoundError(ValueError):
    """Raised when a voice_profile_id cannot be resolved."""

    def __init__(self, profile_id: str) -> None:
        super().__init__(f"Voice profile {profile_id!r} not found.")
        self.profile_id = profile_id


# ---------------------------------------------------------------------------
# Backward compat: old Azure-style voice IDs → voice_profile_id
# Personas written before the voice resolver existed hard-coded Azure voice
# IDs in the ``voice_preference`` field.
# ---------------------------------------------------------------------------

_AZURE_VOICE_TO_PROFILE: dict[str, str] = {
    "zh-CN-XiaoxiaoNeural": "xiaonuan",
    "zh-CN-YunxiNeural": "default",
    "en-US-AriaNeural": "aria",
    "en-US-JennyNeural": "aria",
}

_LEGACY_VOICE_TO_PROFILE: dict[str, str] = {
    "longxiaochun": "default",
    "longyuning": "aria",
    "zh_female_tianmei": "default",
    "en_female_makabaka": "aria",
}


# ---------------------------------------------------------------------------
# Voice profiles
# ---------------------------------------------------------------------------

_DEFAULT_PROFILE = VoiceProfile(
    voice_profile_id="default",
    display_name="Default",
    provider_voices={
        "azure": "zh-CN-XiaoxiaoNeural",
        "dashscope": "longxiaochun",
        "volc": "zh_female_tianmei",
        "volc_realtime": "zh_female_tianmei",
        "local": "piper_huayan",
        "openai": "nova",
        "siliconflow": "longxiaochun",
        "fish_audio": "default",
        "chattts": "default",
        "xiaomi_mimo": "mimo_default",
    },
    sample_rate=22050,
    language="zh-CN",
)

_XIAONUAN_PROFILE = VoiceProfile(
    voice_profile_id="xiaonuan",
    display_name="小暖",
    provider_voices={
        "azure": "zh-CN-XiaoxiaoNeural",
        "dashscope": "longxiaochun",
        "volc": "zh_female_tianmei",
        "volc_realtime": "zh_female_tianmei",
        "local": "piper_huayan",
        "openai": "nova",
        "siliconflow": "longxiaochun",
        "fish_audio": "default",
        "chattts": "default",
        "xiaomi_mimo": "default_zh",
    },
    sample_rate=22050,
    language="zh-CN",
)

_ARIA_PROFILE = VoiceProfile(
    voice_profile_id="aria",
    display_name="Aria",
    provider_voices={
        "azure": "en-US-AriaNeural",
        "dashscope": "longyuning",
        "volc": "en_female_makabaka",
        "volc_realtime": "en_female_makabaka",
        "local": "en_US-lessac-medium",
        "openai": "nova",
        "siliconflow": "longyuning",
        "fish_audio": "default",
        "chattts": "default",
        "xiaomi_mimo": "default_en",
    },
    sample_rate=22050,
    language="en-US",
)

_HUAYAN_PROFILE = VoiceProfile(
    voice_profile_id="huayan",
    display_name="花颜",
    provider_voices={
        "azure": "zh-CN-XiaoxiaoNeural",
        "dashscope": "longxiaochun",
        "volc": "zh_female_tianmei",
        "volc_realtime": "zh_female_tianmei",
        "local": "piper_huayan",
        "openai": "nova",
        "siliconflow": "longxiaochun",
        "fish_audio": "default",
        "chattts": "default",
        "xiaomi_mimo": "mimo_default",
    },
    sample_rate=22050,
    language="zh-CN",
)

_PROFILES: dict[str, VoiceProfile] = {
    "default": _DEFAULT_PROFILE,
    "xiaonuan": _XIAONUAN_PROFILE,
    "aria": _ARIA_PROFILE,
    "huayan": _HUAYAN_PROFILE,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_voice_profile(profile_id: str | None = None) -> VoiceProfile:
    if profile_id and profile_id in _PROFILES:
        return _PROFILES[profile_id]
    return _DEFAULT_PROFILE


def resolve_profile_id(
    raw_voice_preference: str | None = None,
    persona_id: str | None = None,
) -> str:
    """Resolve a raw voice_preference string to a logical voice_profile_id.

    Resolution order:
    1. If ``raw_voice_preference`` is a known voice_profile_id, return it.
    2. Backward compat: map old Azure voice IDs (e.g. "zh-CN-XiaoxiaoNeural" → "xiaonuan").
    3. Legacy compat: map provider-native voice IDs (e.g. "longxiaochun" → "default").
    4. Fall back to ``persona_id`` if it exists in _PROFILES.
    5. Fall back to "default".
    """
    if raw_voice_preference:
        if raw_voice_preference in _PROFILES:
            return raw_voice_preference
        mapped = _AZURE_VOICE_TO_PROFILE.get(raw_voice_preference)
        if mapped:
            return mapped
        mapped = _LEGACY_VOICE_TO_PROFILE.get(raw_voice_preference)
        if mapped:
            return mapped
    if persona_id and persona_id in _PROFILES:
        return persona_id
    return "default"


def resolve_voice(
    provider_name: str,
    profile_id: str | None = None,
    *,
    strict: bool = False,
) -> str:
    """Resolve a provider's concrete voice/speaker ID from a logical voice profile.

    Parameters
    ----------
    provider_name:
        The provider to resolve for (e.g. "dashscope", "volc_realtime", "local").
    profile_id:
        Logical voice profile ID (e.g. "xiaonuan", "aria").  Defaults to "default".
    strict:
        If True, raise ``UnknownProviderError`` when the provider has no mapping.
        If False (default), return "" for unknown providers (backward compat).

    Returns
    -------
    Provider-specific voice ID string.

    Raises
    ------
    UnknownProviderError
        When ``strict=True`` and ``provider_name`` is not in the profile's mapping.
    """
    profile = get_voice_profile(profile_id)
    voice_id = profile.provider_voices.get(provider_name)
    if voice_id is not None:
        return voice_id
    if strict:
        raise UnknownProviderError(provider_name, profile.voice_profile_id)
    return ""


def register_voice_profile(profile: VoiceProfile) -> None:
    _PROFILES[profile.voice_profile_id] = profile


def list_voice_profiles() -> list[str]:
    return list(_PROFILES.keys())


__all__ = [
    "UnknownProviderError",
    "VoiceProfileNotFoundError",
    "get_voice_profile",
    "resolve_profile_id",
    "resolve_voice",
    "register_voice_profile",
    "list_voice_profiles",
]
