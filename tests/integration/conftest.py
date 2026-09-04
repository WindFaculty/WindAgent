"""Shared fixtures for PostgreSQL integration tests (canonical database)."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from windagent.platform.persistence import Database, wait_for_database

DEFAULT_URL = "postgresql+asyncpg://windagent:windagent@localhost:55433/windagent_v2"
V2_ROOT = Path(__file__).resolve().parents[2]
_MIGRATED_URLS: set[str] = set()


@pytest.fixture
def database_url() -> str:
    return os.environ.get("WINDAGENT_DATABASE_URL", DEFAULT_URL)


@pytest.fixture
async def database(database_url: str) -> AsyncIterator[Database]:
    db = Database.from_url(database_url)
    report = await wait_for_database(db.engine, timeout_s=3.0, interval_s=0.25)
    if not report.is_healthy:
        await db.dispose()
        pytest.skip(f"PostgreSQL is not reachable at {db.url}: {report.error}")
    if database_url not in _MIGRATED_URLS:
        environment = {
            **os.environ,
            "WINDAGENT_DATABASE_URL": database_url,
            "WINDAGENT_ENVIRONMENT": "development",
        }
        migration = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=V2_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if migration.returncode != 0:
            await db.dispose()
            pytest.fail(f"integration database migration failed: {migration.stderr}")
        _MIGRATED_URLS.add(database_url)
    try:
        yield db
    finally:
        await db.dispose()
