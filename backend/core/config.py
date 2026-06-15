"""
backend/core/config.py
──────────────────────
Centralised application configuration via pydantic-settings.
All values are read from environment variables or a .env file.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    APP_NAME: str = "OpenSource AI Engineer"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"  # development | staging | production

    # ── Database ───────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/opensource_engineer",
        description="Async PostgreSQL connection URL (asyncpg driver)",
    )
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 1800  # seconds

    # ── Redis ──────────────────────────────────────────────────────────────────
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    REDIS_MAX_CONNECTIONS: int = 20
    REDIS_SOCKET_TIMEOUT: int = 5
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5

    # ── ChromaDB ──────────────────────────────────────────────────────────────
    CHROMADB_HOST: str = "localhost"
    CHROMADB_PORT: int = 8001
    CHROMADB_AUTH_TOKEN: Optional[str] = None

    # ── GitHub ────────────────────────────────────────────────────────────────
    GITHUB_TOKEN: str = Field(default="", description="GitHub personal access token")
    GITHUB_WEBHOOK_SECRET: str = Field(default="", description="GitHub webhook secret")
    GITHUB_API_BASE_URL: str = "https://api.github.com"
    GITHUB_RATE_LIMIT_BUFFER: int = 200  # stop at this many remaining calls

    # ── LLM / AI ──────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key")
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:latest"
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MAX_RETRIES: int = 3
    LLM_REQUEST_TIMEOUT: int = 120  # seconds
    LLM_MAX_TOKENS_CODE: int = 8192
    LLM_MAX_TOKENS_ANALYSIS: int = 4096

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = Field(
        default="CHANGE_ME_IN_PRODUCTION_USE_SECRETS_MODULE_TO_GENERATE",
        description="JWT signing secret – must be changed in production",
    )
    FERNET_KEY: str = Field(
        default="",
        description=(
            "URL-safe base-64 encoded 32-byte key generated via "
            "cryptography.fernet.Fernet.generate_key()"
        ),
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Notifications ─────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    DISCORD_WEBHOOK_URL: Optional[str] = None

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    NOTIFICATION_EMAIL: Optional[str] = None
    SMTP_USE_TLS: bool = True

    # ── Sandbox ───────────────────────────────────────────────────────────────
    SANDBOX_DOCKER_IMAGE: str = "python:3.12-slim"
    SANDBOX_MEMORY_LIMIT: str = "512m"
    SANDBOX_CPU_QUOTA: int = 100000  # 100% of one CPU core
    SANDBOX_TIMEOUT_SECONDS: int = 60
    SANDBOX_NETWORK_DISABLED: bool = True
    SANDBOX_WORK_DIR: str = "/workspace"

    # ── Resilience ────────────────────────────────────────────────────────────
    MAX_RETRIES: int = 3
    CIRCUIT_BREAKER_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RESET_TIMEOUT: int = 60  # seconds

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── APScheduler ───────────────────────────────────────────────────────────
    SCHEDULER_REPO_DISCOVERY_CRON: str = "0 */6 * * *"   # every 6 hours
    SCHEDULER_ISSUE_SCAN_CRON: str = "0 */2 * * *"       # every 2 hours
    SCHEDULER_KNOWLEDGE_SYNC_CRON: str = "0 2 * * *"     # daily at 02:00

    # ── Scoring Weights ───────────────────────────────────────────────────────
    WEIGHT_STARS: float = 0.20
    WEIGHT_ACTIVITY: float = 0.25
    WEIGHT_RESPONSIVENESS: float = 0.30
    WEIGHT_PR_ACCEPTANCE: float = 0.25

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith(("postgresql", "sqlite")):
            raise ValueError("DATABASE_URL must use postgresql or sqlite scheme")
        return v

    @field_validator("FERNET_KEY", mode="before")
    @classmethod
    def validate_fernet_key(cls, v: str) -> str:
        """Auto-generate a Fernet key if none provided (dev convenience)."""
        if not v:
            from cryptography.fernet import Fernet
            import warnings
            warnings.warn(
                "FERNET_KEY not set – auto-generating an ephemeral key. "
                "Encrypted data will NOT survive restarts. Set FERNET_KEY in .env.",
                RuntimeWarning,
                stacklevel=2,
            )
            return Fernet.generate_key().decode()
        return v

    # ── Computed helpers ──────────────────────────────────────────────────────
    @property
    def async_database_url(self) -> str:
        """Ensure asyncpg driver is specified."""
        url = self.DATABASE_URL
        if "postgresql://" in url and "asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://")
        return url

    @property
    def sync_database_url(self) -> str:
        """Return a psycopg2-compatible URL (used by Alembic)."""
        url = self.DATABASE_URL
        url = url.replace("postgresql+asyncpg://", "postgresql://")
        url = url.replace("postgresql+psycopg2://", "postgresql://")
        return url

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def chromadb_url(self) -> str:
        return f"http://{self.CHROMADB_HOST}:{self.CHROMADB_PORT}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()


# Module-level singleton for convenience imports
settings: Settings = get_settings()
