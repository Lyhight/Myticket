from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # -------------------------
    # App
    # -------------------------
    app_name: str = "MyTicket API"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "text"] = "json"
    metrics_bearer_token: str = Field(default="", max_length=256)

    # -------------------------
    # Database
    # -------------------------
    database_url: str = Field(min_length=1)
    database_echo: bool = False
    database_pool_recycle_seconds: int = Field(
        default=1800,
        ge=60,
        le=86_400,
    )

    # -------------------------
    # Redis
    # -------------------------
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    rate_limit_redis_failure_mode: Literal["local", "deny"] = "local"
    rate_limit_key_prefix: str = Field(
        default="myticket:rate-limit",
        min_length=1,
        max_length=100,
    )
    agent_rate_limit_per_minute: int = Field(default=20, ge=1, le=10_000)
    auth_account_rate_limit_per_minute: int = Field(default=10, ge=1, le=1_000)
    auth_ip_rate_limit_per_minute: int = Field(default=60, ge=1, le=10_000)
    agent_worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=60)
    agent_task_lease_seconds: int = Field(default=60, ge=10, le=3_600)
    agent_task_max_attempts: int = Field(default=3, ge=1, le=10)
    agent_worker_metrics_port: int = Field(default=0, ge=0, le=65_535)

    # -------------------------
    # JWT
    # -------------------------
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(default=60, ge=1, le=10_080)
    auth_cookie_name: str = Field(
        default="myticket_session",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    auth_cookie_secure: bool = False

    # -------------------------
    # LLM
    # -------------------------
    llm_provider: str = "qwen"
    llm_enabled: bool = False

    # -------------------------
    # Qwen / DashScope
    # -------------------------
    dashscope_api_key: str = ""

    qwen_model: str = "qwen3.8-max"

    qwen_base_url: str = (
        "https://dashscope.aliyuncs.com/"
        "compatible-mode/v1"
    )

    classification_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    classification_max_retries: int = Field(default=2, ge=0, le=5)
    decision_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    decision_max_retries: int = Field(default=2, ge=0, le=5)
    reply_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    reply_max_retries: int = Field(default=2, ge=0, le=5)
    review_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    review_max_retries: int = Field(default=1, ge=0, le=5)
    llm_retry_delay_seconds: float = Field(default=1.0, ge=0, le=30)
    classification_max_output_tokens: int = Field(default=300, ge=64, le=2_000)
    decision_max_output_tokens: int = Field(default=500, ge=64, le=4_000)
    reply_max_output_tokens: int = Field(default=800, ge=64, le=4_000)
    review_max_output_tokens: int = Field(default=300, ge=64, le=2_000)

    embedding_enabled: bool = False
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = Field(default=512, ge=64, le=2048)
    embedding_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    rag_top_k: int = Field(default=3, ge=1, le=10)
    rag_candidate_k: int = Field(default=10, ge=5, le=100)
    knowledge_chunk_size: int = Field(default=500, ge=100, le=5_000)
    knowledge_chunk_overlap: int = Field(default=80, ge=0, le=1_000)
    knowledge_max_chunks: int = Field(default=200, ge=1, le=1_000)
    knowledge_embedding_total_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        le=600,
    )

    context_max_history_characters: int = Field(default=6000, ge=100, le=100_000)
    context_max_messages: int = Field(default=12, ge=1, le=100)
    context_max_tool_results: int = Field(default=3, ge=0, le=20)
    context_max_characters: int = Field(default=9000, ge=500, le=200_000)
    context_max_memory_characters: int = Field(default=1500, ge=0, le=50_000)
    context_max_knowledge_characters: int = Field(default=3000, ge=0, le=100_000)

    @model_validator(mode="after")
    def validate_related_limits(self) -> "Settings":
        if self.rag_candidate_k < self.rag_top_k:
            raise ValueError("rag_candidate_k must be at least rag_top_k")
        if self.context_max_history_characters > self.context_max_characters:
            raise ValueError(
                "context history budget cannot exceed total context budget"
            )
        if self.knowledge_chunk_overlap >= self.knowledge_chunk_size:
            raise ValueError(
                "knowledge_chunk_overlap must be smaller than chunk size"
            )
        if (self.llm_enabled or self.embedding_enabled) and not (
            self.dashscope_api_key.strip()
        ):
            raise ValueError(
                "dashscope_api_key is required when LLM or embedding is enabled"
            )
        return self

    # -------------------------
    # Pydantic Settings
    # -------------------------
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
