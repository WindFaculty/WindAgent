"""Phase 4 — demo profile gating.

Verifies that demo seeding is opt-in:
- Default startup (no WINDAGENT_PROFILE) leaves a fresh DB free of demo records.
- Explicit WINDAGENT_PROFILE=demo startup seeds idempotently.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from windagent_api.services.v3_demo_seed import NS_PROJECTS, seed_demo_data
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.v3_resource_repository import (
    SQLV3ResourceRepository,
)


def _make_service(db: DatabaseManager) -> V3ResourceService:
    return V3ResourceService(
        uow_factory=lambda: _uow(db),
        repository_factory=lambda session: SQLV3ResourceRepository(session),
    )


def _uow(db: DatabaseManager):
    from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

    return SqlUnitOfWork(db.session_factory)


@pytest.fixture
def fresh_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'demo.db'}")
    asyncio.run(db.upgrade_to_head(BaseORM.metadata))
    yield db
    asyncio.run(db.close())


def test_default_startup_leaves_fresh_db_free_of_demo_records(fresh_db):
    """Without WINDAGENT_PROFILE=demo, no demo records are installed."""
    service = _make_service(fresh_db)
    projects = asyncio.run(service.list(NS_PROJECTS))
    assert projects == []


def test_explicit_demo_startup_seeds_idempotently(fresh_db):
    """With WINDAGENT_PROFILE=demo, seeding installs records and is idempotent."""
    service = _make_service(fresh_db)
    asyncio.run(seed_demo_data(service))
    first = asyncio.run(service.list(NS_PROJECTS))
    assert len(first) >= 1

    # Seeding again must not duplicate records.
    asyncio.run(seed_demo_data(service))
    second = asyncio.run(service.list(NS_PROJECTS))
    assert len(second) == len(first)
    ids_first = {p["id"] for p in first}
    ids_second = {p["id"] for p in second}
    assert ids_first == ids_second


def test_lifespan_gating_uses_profile_env(monkeypatch, tmp_path):
    """The lifespan seeding decision keys off WINDAGENT_PROFILE=demo."""
    from windagent_api import lifespan as lifespan_module

    # Default: no demo.
    monkeypatch.delenv("WINDAGENT_PROFILE", raising=False)
    assert lifespan_module._demo_profile_enabled() is False

    # Explicit demo.
    monkeypatch.setenv("WINDAGENT_PROFILE", "demo")
    assert lifespan_module._demo_profile_enabled() is True

    # Other profiles are not demo.
    monkeypatch.setenv("WINDAGENT_PROFILE", "development")
    assert lifespan_module._demo_profile_enabled() is False
