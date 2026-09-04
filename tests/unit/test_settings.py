"""Settings startup rules (plan section 8: PostgreSQL is canonical)."""

from __future__ import annotations

import pytest
from windagent.platform.configuration.settings import (
    DEFAULT_DATABASE_URL,
    Settings,
    SQLiteNotAllowedError,
)

SQLITE_URL = "sqlite+aiosqlite:///./windagent_v2.db"


def test_default_configuration_is_postgres_asyncpg() -> None:
    settings = Settings(environment="development")
    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_sqlite_is_rejected_outside_test_environment() -> None:
    with pytest.raises(SQLiteNotAllowedError):
        Settings(environment="development", database_url=SQLITE_URL)
    with pytest.raises(SQLiteNotAllowedError):
        Settings(environment="production", database_url=SQLITE_URL)


def test_sqlite_is_allowed_for_isolated_unit_tests() -> None:
    settings = Settings(environment="test", database_url=SQLITE_URL)
    assert settings.database_url == SQLITE_URL


def test_environment_variables_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WINDAGENT_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "WINDAGENT_DATABASE_URL",
        "postgresql+asyncpg://prod@db.internal:5432/windagent_v2",
    )
    settings = Settings()
    assert settings.environment == "production"
    assert settings.database_url.startswith("postgresql+asyncpg://prod@")


def test_invalid_environment_is_rejected() -> None:
    from typing import cast

    from windagent.platform.configuration.settings import Environment

    with pytest.raises(ValueError):
        Settings(environment=cast("Environment", "staging"))
