"""Phase 5 unit tests: Database engine factory (canonical PostgreSQL only)."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import QueuePool
from windagent.platform.configuration.settings import Environment, Settings
from windagent.platform.persistence import (
    Database,
    NonCanonicalDatabaseError,
    SqlUnitOfWork,
)

PG_URL = "postgresql+asyncpg://windagent:windagent@localhost:55433/windagent_v2"


def test_from_url_builds_canonical_engine_with_default_pool() -> None:
    db = Database.from_url(PG_URL)

    assert db.url == "postgresql+asyncpg://windagent:***@localhost:55433/windagent_v2"
    assert isinstance(db.session_factory, async_sessionmaker)
    pool = db.engine.pool
    assert isinstance(pool, QueuePool)
    assert pool.size() == 10


def test_from_url_masks_credentials_in_public_surface() -> None:
    db = Database.from_url(PG_URL)

    assert "windagent:windagent" not in repr(db)
    assert "***" in repr(db)


def test_pool_options_are_configurable() -> None:
    db = Database.from_url(PG_URL, pool_size=2, max_overflow=3)

    pool = db.engine.pool
    assert isinstance(pool, QueuePool)
    assert pool.size() == 2


@pytest.mark.parametrize("environment", ["development", "production"])
def test_non_canonical_scheme_is_rejected_outside_tests(environment: str) -> None:
    with pytest.raises(NonCanonicalDatabaseError):
        Database.from_url(
            "sqlite+aiosqlite:///./probe.db",
            environment=cast(Environment, environment),
        )


def test_isolated_test_environment_may_use_other_schemes() -> None:
    db = Database.from_url("sqlite+aiosqlite:///./probe.db", environment="test")

    assert isinstance(db.session_factory, async_sessionmaker)


def test_from_settings_uses_configured_url_and_environment() -> None:
    settings = Settings(environment="development")

    db = Database.from_settings(settings)

    assert db.url == "postgresql+asyncpg://windagent:***@localhost:55433/windagent_v2"


def test_unit_of_work_returns_independent_scopes() -> None:
    db = Database.from_url(PG_URL)

    first = db.unit_of_work()
    second = db.unit_of_work()

    assert isinstance(first, SqlUnitOfWork)
    assert first is not second


async def test_dispose_completes_without_connections() -> None:
    db = Database.from_url(PG_URL)

    await db.dispose()
