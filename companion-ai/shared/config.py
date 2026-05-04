"""Global configuration loaded from environment variables."""

from functools import lru_cache
from typing import List, Optional

from pydantic import ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All companion-ai services read from the same env prefix."""

    model_config = ConfigDict(
        env_prefix="COMPANION_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        str_strip_whitespace=True,
    )

    # ------------------------------------------------------------------
    # Service identity
    # ------------------------------------------------------------------
    service_name: str = Field(default="companion-ai")
    service_port: int = Field(default=8000)
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
    mqtt_username: Optional[str] = Field(default=None)
    mqtt_password: Optional[str] = Field(default=None)

    # ------------------------------------------------------------------
    # LLM providers (cloud API only)
    # ------------------------------------------------------------------
    openai_api_key: Optional[str] = Field(default=None)
    openai_base_url: Optional[str] = Field(default=None)
    anthropic_api_key: Optional[str] = Field(default=None)
    anthropic_base_url: Optional[str] = Field(default=None)
    default_llm_model: str = Field(default="gpt-4o")
    reasoning_llm_model: str = Field(default="o3-mini")

    # ------------------------------------------------------------------
    # Voice (cloud API)
    # ------------------------------------------------------------------
    whisper_api_key: Optional[str] = Field(default=None)
    whisper_base_url: Optional[str] = Field(default=None)
    tts_provider: str = Field(default="fish_audio")  # fish_audio | chattts | openai
    tts_api_key: Optional[str] = Field(default=None)
    tts_base_url: Optional[str] = Field(default=None)
    default_voice_id: str = Field(default="zh-CN-XiaoxiaoNeural")

    # ------------------------------------------------------------------
    # Action / 2D generation
    # ------------------------------------------------------------------
    action_provider: str = Field(default="tongyi")  # tongyi | custom
    action_api_key: Optional[str] = Field(default=None)
    action_base_url: Optional[str] = Field(default=None)
    avatar_2d_reference_url: Optional[str] = Field(default=None)

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    jwt_secret: str = Field(default="change-me-in-production")
    encryption_key: Optional[str] = Field(default=None)

    # ------------------------------------------------------------------
    # Feature flags
    # ------------------------------------------------------------------
    enable_voice: bool = Field(default=True)
    enable_action_2d: bool = Field(default=True)
    enable_memory_pipeline: bool = Field(default=True)
    enable_device_coordination: bool = Field(default=True)
    enable_knowledge_graph: bool = Field(default=True)

    # ------------------------------------------------------------------
    # Lite mode (local dev without Docker)
    # ------------------------------------------------------------------
    lite_mode: bool = Field(default=False)
    """When True, replaces Redis/Postgres/Neo4j with in-memory/SQLite fallbacks."""

    monolithic: bool = Field(default=False)
    """When True, core_orchestrator calls LLM/persona logic in-process instead of via HTTP."""

    @model_validator(mode="before")
    @classmethod
    def _strip_whitespace(cls, values: dict) -> dict:
        return {k: v.strip() if isinstance(v, str) else v for k, v in values.items()}

@lru_cache
def get_settings() -> Settings:
    return Settings()
