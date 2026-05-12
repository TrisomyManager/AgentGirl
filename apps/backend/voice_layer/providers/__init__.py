"""Voice provider implementations.

Each provider module encapsulates a single vendor SDK / API so that
``voice_layer/asr.py`` and ``voice_layer/tts.py`` never directly import
vendor packages. The orchestrator (or host) can inject any provider
implementing ``ASRProvider`` / ``TTSProvider`` Protocol from
``shared_contracts``.
"""

from voice_layer.providers.dashscope import DashScopeASRProvider

__all__ = ["DashScopeASRProvider"]
