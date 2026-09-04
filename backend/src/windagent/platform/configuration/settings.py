"""Application settings.

PostgreSQL is the only canonical database for V2 (plan section 8).  A
``sqlite://`` URL is rejected at startup outside of the ``test`` environment
so the old project's default-SQLite drift cannot be inherited.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://windagent:windagent@localhost:55433/windagent_v2"
)


class SQLiteNotAllowedError(RuntimeError):
    """Startup error raised when a non-canonical database is configured."""


class Settings(BaseSettings):
    """Environment-driven settings shared by all V2 applications."""

    model_config = SettingsConfigDict(
        env_prefix="WINDAGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = "development"
    database_url: str = DEFAULT_DATABASE_URL

    # Security foundation (plan section 13).  Authentication is off by
    # default only for local development; production deployments set
    # WINDAGENT_AUTH_ENABLED=true and provision the token signing secret.
    auth_enabled: bool = False
    # Zero disables HTTP rate limiting entirely.
    rate_limit_per_minute: int = Field(default=0, ge=0)

    # Phase 10 observability. Metrics are bounded in-process and can be
    # replaced by another Telemetry adapter at the composition root.
    metrics_enabled: bool = True
    log_level: LogLevel = "INFO"

    @model_validator(mode="after")
    def _enforce_canonical_database(self) -> Settings:
        is_sqlite = self.database_url.lower().startswith("sqlite")
        if is_sqlite and self.environment != "test":
            raise SQLiteNotAllowedError(
                "SQLite is not a supported V2 database; use "
                "postgresql+asyncpg:// (SQLite is reserved for isolated "
                "unit tests running with WINDAGENT_ENVIRONMENT=test)"
            )
        return self
