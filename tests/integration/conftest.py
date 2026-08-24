"""Integration-tier conftest — multi-component composition (T1).

Provides:

* ``integration_db`` — async DB with full schema for multi-service wiring
* ``isolated_encryption_key`` — AES-GCM key for provider tests
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM


@pytest_asyncio.fixture
async def integration_db(tmp_path, monkeypatch):
    from tests.support.db import isolated_db_url

    url = isolated_db_url(tmp_path)
    monkeypatch.setenv("WINDAGENT_DATABASE_URL", url)
    db = DatabaseManager(url)
    await db.create_tables(BaseORM.metadata)
    yield db
    await db.close()


@pytest.fixture
def isolated_encryption_key(monkeypatch):
    from tests.support.db import fresh_encryption_key

    return fresh_encryption_key(monkeypatch)
