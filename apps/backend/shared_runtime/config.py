"""Global configuration loaded from environment variables.

P1-D 物理搬迁完成 (V2.1): 原 ``shared.config`` 的物理实现现在位于本文件;
``shared.config`` 反向 re-export 兼容老 import. 业务侧应优先
``from shared_runtime import Settings, get_settings``.

注意: ``.env`` 位于后端根目录 ``apps/backend/.env``; 本模块用绝对路径解析以避免
被 uvicorn 启动 cwd 影响.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings

# apps/backend/.env — absolute path so uvicorn cwd does not affect lite_mode / keys.
# 本文件位于 apps/backend/shared_runtime/config.py, 父父级即 apps/backend/.
_COMPANION_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """All companion-ai services read from the same env prefix."""

    model_config = ConfigDict(
        env_prefix="COMPANION_",
        env_file=_COMPANION_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="allow",
        str_strip_whitespace=True,
    )

    # ------------------------------------------------------------------
    # Service identity
    # ------------------------------------------------------------------
    service_name: str = Field(default="companion-ai")
    service_port: int = Field(
        default=8000,
        description="HTTP port for this process when building default loopback URLs (uvicorn --port).",
    )

    self_base_url: str | None = Field(
        default=None,
        description=(
            "Absolute base URL of this companion HTTP app for internal clients "
            "(e.g. http://127.0.0.1:9000). Env: COMPANION_SELF_BASE_URL. "
            "When unset, defaults to http://127.0.0.1:{service_port}."
        ),
    )

    log_level: str = Field(default="INFO")

    # ------------------------------------------------------------------
    # Redis (event bus + short-term cache)
    # ------------------------------------------------------------------
    redis_url: str = Field(default="redis://localhost:6379/0")
    redis_pubsub_channel_prefix: str = Field(default="companion")

    # ------------------------------------------------------------------
    # PostgreSQL + pgvector
    # ------------------------------------------------------------------
    postgres_url: str = Field(default="postgresql://user:pass@localhost:5432/companion")

    # ------------------------------------------------------------------
    # Neo4j
    # ------------------------------------------------------------------
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="password")

    # ------------------------------------------------------------------
    # MQTT (cross-device)
    # ------------------------------------------------------------------
    mqtt_broker_host: str = Field(default="localhost")
    mqtt_broker_port: int = Field(default=1883)
    mqtt_username: str | None = Field(default=None)
    mqtt_password: str | None = Field(default=None)

    # ------------------------------------------------------------------
    # LLM providers (cloud API only)
    # ------------------------------------------------------------------
    openai_api_key: str | None = Field(default=None)
    openai_base_url: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)
    anthropic_base_url: str | None = Field(default=None)
    default_llm_model: str = Field(default="gpt-4o")
    reasoning_llm_model: str = Field(default="o3-mini")

    # ------------------------------------------------------------------
    # Voice (cloud API)
    # ------------------------------------------------------------------
    whisper_api_key: str | None = Field(default=None)
    whisper_base_url: str | None = Field(default=None)
    tts_provider: str = Field(default="fish_audio")  # fish_audio | chattts | openai
    tts_api_key: str | None = Field(default=None)
    tts_base_url: str | None = Field(default=None)
    default_voice_id: str = Field(default="zh-CN-XiaoxiaoNeural")

    # ------------------------------------------------------------------
    # Volcengine realtime voice (火山引擎端到端实时语音)
    # ------------------------------------------------------------------
    realtime_voice_provider: str = Field(default="cloud")  # local | cloud | volc_realtime
    volc_app_id: str | None = Field(default=None)
    volc_access_token: str | None = Field(default=None)
    volc_resource_id: str = Field(default="volc.speech.dialog")
    volc_endpoint: str = Field(default="wss://openspeech.bytedance.com/api/v3/realtime/dialogue")

    # ------------------------------------------------------------------
    # Action / 2D generation
    # ------------------------------------------------------------------
    action_provider: str = Field(default="tongyi")  # tongyi | custom
    action_api_key: str | None = Field(default=None)
    action_base_url: str | None = Field(default=None)
    avatar_2d_reference_url: str | None = Field(default=None)

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    jwt_secret: str = Field(default="change-me-in-production")
    encryption_key: str | None = Field(default=None)

    # ------------------------------------------------------------------
    # Feature flags
    # ------------------------------------------------------------------
    enable_voice: bool = Field(default=True)
    enable_action_2d: bool = Field(default=True)
    enable_memory_pipeline: bool = Field(default=True)
    enable_device_coordination: bool = Field(default=True)
    enable_knowledge_graph: bool = Field(default=True)

    # ------------------------------------------------------------------
    # Working memory (per-session prompt context)
    # ------------------------------------------------------------------
    working_memory_llm_summary: bool = Field(default=False)
    """When True and an LLM key is configured, refine ``dominant_topic`` via a tiny completion."""

    working_memory_llm_digest: bool = Field(default=False)
    """When True and an LLM key is configured, add a one-line ``session_digest`` for the prompt."""

    working_memory_summary_model: str | None = Field(default=None)
    """Optional model override for working-memory LLM calls (defaults to ``default_llm_model``)."""

    working_memory_summary_ttl_seconds: float = Field(default=45.0, ge=5.0, le=600.0)
    """Skip repeat LLM calls for the same session when transcript fingerprint unchanged within TTL."""

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"
    )
    """Comma-separated list of allowed CORS origins. Set to '*' to allow all (not recommended for production)."""

    # ------------------------------------------------------------------
    # Lite mode (local dev without Docker)
    # ------------------------------------------------------------------
    lite_mode: bool = Field(default=False)
    """When True, replaces Redis/Postgres/Neo4j with in-memory/SQLite fallbacks."""

    device_command_ttl_seconds: int = Field(
        default=300,
        ge=30,
        le=86400,
        description="Device gateway: commands expire if not finished within this many seconds.",
    )

    monolithic: bool = Field(default=False)
    """When True, core_orchestrator calls LLM/persona logic in-process instead of via HTTP."""

    @model_validator(mode="before")
    @classmethod
    def _strip_whitespace(cls, values: dict) -> dict:
        return {k: v.strip() if isinstance(v, str) else v for k, v in values.items()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "get_settings"]
