"""Component-tier conftest — single-component + SQLite infra (T1).

Provides:

* ``component_db`` — async ``DatabaseManager`` with full schema
* ``component_session_factory`` — sync ``sessionmaker`` for repository tests
* ``sync_engine_with_tables`` — low-level sync engine for P01-style tests
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from tests.support.db import P01_TABLES, fresh_encryption_key, isolated_db_url
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM


@pytest_asyncio.fixture
async def component_db(tmp_path, monkeypatch):
    """Async DB with full schema — use for ``SqlUnitOfWork`` / repository tests."""
    url = isolated_db_url(tmp_path)
    monkeypatch.setenv("WINDAGENT_DATABASE_URL", url)
    db = DatabaseManager(url)
    await db.create_tables(BaseORM.metadata)
    yield db
    await db.close()


@pytest.fixture
def component_session_factory(tmp_path, monkeypatch):
    """Sync sessionmaker for provider / routing tests (P01-style)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    url = f"sqlite:///{(tmp_path / 'component.db').as_posix()}"
    engine = create_engine(url)
    BaseORM.metadata.create_all(engine, tables=list(P01_TABLES))
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    # also set encryption key for tests that need it
    fresh_encryption_key(monkeypatch)
    yield factory
    engine.dispose()


@pytest.fixture
def sync_engine_with_tables(tmp_path):
    """Raw sync engine — caller decides which tables to create."""
    from sqlalchemy import create_engine

    url = f"sqlite:///{(tmp_path / 'raw.db').as_posix()}"
    engine = create_engine(url)
    yield engine
    engine.dispose()
