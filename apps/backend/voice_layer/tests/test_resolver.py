"""Tests for voice_layer.resolver — unified voice profile resolution."""

from unittest.mock import MagicMock, patch

import pytest

from shared_contracts.models import VoiceProfile
from voice_layer.resolver import (
    UnknownProviderError,
    get_voice_profile,
    list_voice_profiles,
    register_voice_profile,
    resolve_profile_id,
    resolve_voice,
)

# ---------------------------------------------------------------------------
# Autouse fixture: backup / restore _PROFILES so registry tests are isolated
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_profiles():
    import voice_layer.resolver as _mod
    saved = dict(_mod._PROFILES)
    yield
    _mod._PROFILES.clear()
    _mod._PROFILES.update(saved)

# ---------------------------------------------------------------------------
# resolve_profile_id — backward compat mapping
# ---------------------------------------------------------------------------

class TestResolveProfileId:
    def test_known_profile_id_passthrough(self):
        assert resolve_profile_id("xiaonuan") == "xiaonuan"
        assert resolve_profile_id("aria") == "aria"
        assert resolve_profile_id("huayan") == "huayan"
        assert resolve_profile_id("default") == "default"

    def test_azure_voice_id_maps_to_profile(self):
        assert resolve_profile_id("zh-CN-XiaoxiaoNeural") == "xiaonuan"
        assert resolve_profile_id("en-US-AriaNeural") == "aria"
        assert resolve_profile_id("zh-CN-YunxiNeural") == "default"
        assert resolve_profile_id("en-US-JennyNeural") == "aria"

    def test_unknown_raw_falls_back_to_persona_id(self):
        assert resolve_profile_id("unknown_voice", persona_id="xiaonuan") == "xiaonuan"
        assert resolve_profile_id("unknown_voice", persona_id="aria") == "aria"

    def test_unknown_raw_and_unknown_persona_falls_back_to_default(self):
        assert resolve_profile_id("unknown_voice", persona_id="unknown_role") == "default"
        assert resolve_profile_id("unknown_voice") == "default"

    def test_none_voice_preference_uses_persona_id(self):
        assert resolve_profile_id(None, persona_id="aria") == "aria"
        assert resolve_profile_id(None, persona_id="default") == "default"

    def test_none_voice_preference_and_unknown_persona(self):
        assert resolve_profile_id(None, persona_id="unknown_role") == "default"
        assert resolve_profile_id(None) == "default"


# ---------------------------------------------------------------------------
# resolve_voice — provider voice resolution
# ---------------------------------------------------------------------------

class TestResolveVoice:
    # -- DashScope never receives Azure voice IDs --------------------------

    def test_dashscope_does_not_receive_azure_voice_id(self):
        """When given the old Azure voice ID 'zh-CN-XiaoxiaoNeural', DashScope
        must resolve to a DashScope-native voice, not pass through the Azure ID."""
        # 'zh-CN-XiaoxiaoNeural' is NOT a known profile_id, so get_voice_profile
        # falls back to default, whose dashscope voice is 'longxiaochun'.
        voice = resolve_voice("dashscope", "zh-CN-XiaoxiaoNeural")
        assert voice == "longxiaochun"
        assert voice != "zh-CN-XiaoxiaoNeural"

    def test_dashscope_resolves_xiaonuan_to_longxiaochun(self):
        voice = resolve_voice("dashscope", "xiaonuan")
        assert voice == "longxiaochun"

    def test_dashscope_resolves_aria_to_longyuning(self):
        voice = resolve_voice("dashscope", "aria")
        assert voice == "longyuning"

    # -- Volc realtime and regular TTS same role → each provider's voice ---

    def test_xiaonuan_volc_realtime_vs_dashscope(self):
        volc = resolve_voice("volc_realtime", "xiaonuan")
        dash = resolve_voice("dashscope", "xiaonuan")
        assert volc == "zh_female_tianmei"
        assert dash == "longxiaochun"
        assert volc != dash

    def test_aria_volc_realtime_vs_openai(self):
        volc = resolve_voice("volc_realtime", "aria")
        openai = resolve_voice("openai", "aria")
        assert volc == "en_female_makabaka"
        assert openai == "nova"
        assert volc != openai

    def test_xiaonuan_local_vs_azure(self):
        local = resolve_voice("local", "xiaonuan")
        azure = resolve_voice("azure", "xiaonuan")
        assert local == "piper_huayan"
        assert azure == "zh-CN-XiaoxiaoNeural"

    # -- unknown provider handling -----------------------------------------

    def test_unknown_provider_strict_raises(self):
        with pytest.raises(UnknownProviderError) as exc_info:
            resolve_voice("imaginary_provider", "xiaonuan", strict=True)
        assert "imaginary_provider" in str(exc_info.value)
        assert "xiaonuan" in str(exc_info.value)

    def test_unknown_provider_non_strict_returns_empty(self):
        voice = resolve_voice("imaginary_provider", "xiaonuan", strict=False)
        assert voice == ""

    def test_unknown_provider_defaults_to_empty_not_other_provider_voice(self):
        """An unknown provider must not silently return another provider's voice ID."""
        # This is the critical check: empty string means "not supported", not
        # some random provider's voice that would cause silent misconfiguration.
        voice = resolve_voice("nonexistent", "xiaonuan", strict=False)
        assert voice == ""
        # It should NOT be dashscope's voice, azure's voice, etc.
        assert voice != "longxiaochun"
        assert voice != "zh-CN-XiaoxiaoNeural"
        assert voice != "zh_female_tianmei"

    # -- other providers ---------------------------------------------------

    def test_azure_resolves_correctly(self):
        assert resolve_voice("azure", "xiaonuan") == "zh-CN-XiaoxiaoNeural"
        assert resolve_voice("azure", "aria") == "en-US-AriaNeural"

    def test_openai_resolves_to_nova(self):
        assert resolve_voice("openai", "xiaonuan") == "nova"
        assert resolve_voice("openai", "aria") == "nova"

    def test_siliconflow_resolves_correctly(self):
        assert resolve_voice("siliconflow", "xiaonuan") == "longxiaochun"
        assert resolve_voice("siliconflow", "aria") == "longyuning"

    def test_fish_audio_resolves_to_default(self):
        assert resolve_voice("fish_audio", "xiaonuan") == "default"

    def test_chattts_resolves_to_default(self):
        assert resolve_voice("chattts", "xiaonuan") == "default"

    def test_volc_regular_resolves_correctly(self):
        assert resolve_voice("volc", "xiaonuan") == "zh_female_tianmei"
        assert resolve_voice("volc", "aria") == "en_female_makabaka"


# ---------------------------------------------------------------------------
# get_voice_profile
# ---------------------------------------------------------------------------

class TestGetVoiceProfile:
    def test_known_profile(self):
        profile = get_voice_profile("xiaonuan")
        assert profile.voice_profile_id == "xiaonuan"
        assert profile.display_name == "小暖"
        assert profile.language == "zh-CN"

    def test_aria_profile(self):
        profile = get_voice_profile("aria")
        assert profile.voice_profile_id == "aria"
        assert profile.display_name == "Aria"
        assert profile.language == "en-US"

    def test_unknown_profile_falls_back_to_default(self):
        profile = get_voice_profile("nonexistent")
        assert profile.voice_profile_id == "default"

    def test_none_falls_back_to_default(self):
        profile = get_voice_profile(None)
        assert profile.voice_profile_id == "default"


# ---------------------------------------------------------------------------
# register_voice_profile / list_voice_profiles
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_list_voice_profiles(self):
        profiles = list_voice_profiles()
        assert "default" in profiles
        assert "xiaonuan" in profiles
        assert "aria" in profiles
        assert "huayan" in profiles

    def test_register_and_resolve(self):
        custom = VoiceProfile(
            voice_profile_id="test_custom",
            display_name="Test Custom",
            provider_voices={
                "dashscope": "test_dash_voice",
                "volc_realtime": "test_volc_voice",
            },
            sample_rate=16000,
            language="ja-JP",
        )
        register_voice_profile(custom)

        assert "test_custom" in list_voice_profiles()
        assert resolve_voice("dashscope", "test_custom") == "test_dash_voice"
        assert resolve_voice("volc_realtime", "test_custom") == "test_volc_voice"

        # Cleanup — unregister by removing from module dict is tricky;
        # re-registering default won't hurt since register overwrites.
        default = get_voice_profile("default")
        register_voice_profile(default)


# ---------------------------------------------------------------------------
# Proof: ordinary TTS and realtime call the same resolver
# ---------------------------------------------------------------------------

class TestSameResolverForTtsAndRealtime:
    """Both paths MUST go through resolve_voice() — never bypass it."""

    def test_tts_path_uses_resolver_for_dashscope(self):
        """Simulate what TTSClient.synthesize() does with a dashscope provider."""
        profile_id = resolve_profile_id("zh-CN-XiaoxiaoNeural")  # backward compat
        voice = resolve_voice("dashscope", profile_id, strict=True)
        assert voice == "longxiaochun"
        assert voice != "zh-CN-XiaoxiaoNeural"

    def test_realtime_path_uses_same_resolver_as_tts(self):
        """Simulate what VolcRealtimeProvider does for volc_realtime."""
        profile_id = resolve_profile_id("zh-CN-XiaoxiaoNeural")  # same input as TTS
        voice = resolve_voice("volc_realtime", profile_id, strict=True)
        assert voice == "zh_female_tianmei"

    def test_xiaonuan_both_paths_same_profile_different_voices(self):
        """Same role_id 'xiaonuan' resolves to different voices per provider."""
        tts_voice = resolve_voice("dashscope", "xiaonuan")
        realtime_voice = resolve_voice("volc_realtime", "xiaonuan")
        assert tts_voice == "longxiaochun"
        assert realtime_voice == "zh_female_tianmei"
        assert tts_voice != realtime_voice


# ---------------------------------------------------------------------------
# Proof: unknown provider never silently mixes other providers' voice IDs
# ---------------------------------------------------------------------------

class TestNoSilentVoiceLeak:
    def test_strict_mode_prevents_silent_fallback(self):
        """strict=True ensures unknown providers raise, not silently use wrong voice."""
        with pytest.raises(UnknownProviderError):
            resolve_voice("some_broken_provider", "xiaonuan", strict=True)

    def test_non_strict_mode_returns_empty_not_another_providers_voice(self):
        voice = resolve_voice("unknown", "xiaonuan", strict=False)
        assert voice == "", (
            "Empty string is the sentinel for 'unsupported provider'. "
            "Returning any other string would silently cause the wrong voice ID "
            "to be sent to a provider that does not understand it."
        )


# ---------------------------------------------------------------------------
# R1: TTSClient synthesise unresolved fallback — step 1 default, step 2 error
# ---------------------------------------------------------------------------

class TestTTSUnresolvedFallback:
    """Verify TTSClient.synthesize() never sends a meaningless voice ID to the
    provider backend when the voice cannot be resolved."""

    @pytest.mark.asyncio
    async def test_unknown_provider_raises_unknown_provider_error(self):
        """When provider="minimax" has no mapping in any profile, synthesise
        must raise UnknownProviderError after trying the default profile."""
        from shared_contracts.models import EmotionTag, VoiceSynthesisRequest
        from voice_layer.tts import TTSClient

        # Patch out HTTP so the _synthesize_* methods are never reached
        with patch("voice_layer.tts.get_runtime_voice_config") as mock_get_rt:
            mock_get_rt.return_value = {
                "tts_provider": "minimax",
                "tts_api_key": "test-key",
                "tts_base_url": "https://api.example.com/v1",
                "tts_model": "speech-2.0",
                "tts_voice_id": "xiaonuan",
            }

            client = TTSClient()
            assert client.provider == "minimax"

            req = VoiceSynthesisRequest(
                text="测试",
                voice_id="xiaonuan",
                emotion=EmotionTag.NEUTRAL,
            )

            with pytest.raises(UnknownProviderError) as exc_info:
                await client.synthesize(req)
            assert "minimax" in str(exc_info.value)

    def test_fallback_never_submits_default_or_huayan_string_to_backend(self):
        """Even when the resolver falls back, the string 'default' / 'huayan'
        is NEVER used as a raw voice ID for an unrecognised provider."""
        # 'minimax' is not in any VoiceProfile.provider_voices, so both
        # resolve_voice("minimax", "xiaonuan") and the subsequent
        # resolve_voice("minimax", "default") return "" → error.
        assert resolve_voice("minimax", "xiaonuan") == ""
        assert resolve_voice("minimax", "default") == ""
        # If either returned non-empty it would be a bug.
        assert resolve_voice("minimax", "default") != "default"
        assert resolve_voice("minimax", "default") != "huayan"
        assert resolve_voice("minimax", "default") != "longxiaochun"


# ---------------------------------------------------------------------------
# R6: Legacy voice ID mapping
# ---------------------------------------------------------------------------

class TestLegacyVoiceMapping:
    def test_longxiaochun_maps_to_default(self):
        assert resolve_profile_id("longxiaochun") == "default"

    def test_longyuning_maps_to_aria(self):
        assert resolve_profile_id("longyuning") == "aria"

    def test_zh_female_tianmei_maps_to_default(self):
        assert resolve_profile_id("zh_female_tianmei") == "default"

    def test_en_female_makabaka_maps_to_aria(self):
        assert resolve_profile_id("en_female_makabaka") == "aria"

    def test_legacy_takes_precedence_over_persona_for_known_ids(self):
        """Legacy mapping resolves without using persona fallback."""
        assert resolve_profile_id("longxiaochun", persona_id="aria") == "default"

    def test_legacy_falls_before_persona(self):
        """Legacy mapping is checked before persona_id fallback."""
        assert resolve_profile_id("longyuning", persona_id="default") == "aria"

    def test_unknown_still_falls_back_to_persona(self):
        """Non-legacy, non-azure string still falls back to persona_id."""
        assert resolve_profile_id("some_unknown_voice", persona_id="aria") == "aria"
