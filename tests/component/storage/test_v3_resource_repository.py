"""Phase 4 — SQLV3ResourceRepository atomicity, concurrency, and idempotency.

Covers:
- Atomic compare-and-swap update rejects a stale expected version.
- Concurrent stale-version updates cannot both succeed.
- Durable idempotency across a new session/container (same DB file).
- Duplicate idempotent creation returns the existing row deterministically.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.v3_resource_repository import (
    SQLV3ResourceRepository,
)


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    manager = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'repo.db'}")
    asyncio.run(manager.upgrade_to_head(BaseORM.metadata))
    yield manager
    asyncio.run(manager.close())


def _repo(db: DatabaseManager):
    return SQLV3ResourceRepository


async def _create(db: DatabaseManager, namespace, resource_id, data, idem=None):
    async with db.session_factory() as session:
        repo = SQLV3ResourceRepository(session)
        result = await repo.create(namespace, resource_id, data, idem)
        await session.commit()
        return result


async def _get(db: DatabaseManager, namespace, resource_id):
    async with db.session_factory() as session:
        repo = SQLV3ResourceRepository(session)
        return await repo.get(namespace, resource_id)


def test_stale_version_update_rejected(db):
    async def _run():
        await _create(db, "projects", "p1", {"name": "A"})
        # Correct version succeeds.
        async with db.session_factory() as session:
            repo = SQLV3ResourceRepository(session)
            updated = await repo.update("projects", "p1", {"name": "B"}, 1)
            assert updated is not None
            assert updated["version"] == 2
            await session.commit()
        # Stale version (1) is now rejected.
        async with db.session_factory() as session:
            repo = SQLV3ResourceRepository(session)
            stale = await repo.update("projects", "p1", {"name": "C"}, 1)
            assert stale is None
            await session.commit()
        # Current version (2) still works.
        async with db.session_factory() as session:
            repo = SQLV3ResourceRepository(session)
            ok = await repo.update("projects", "p1", {"name": "C"}, 2)
            assert ok is not None
            assert ok["version"] == 3
            await session.commit()

    asyncio.run(_run())


def test_concurrent_stale_version_updates_only_one_succeeds(db):
    """Two concurrent updates with the same expected version: exactly one wins."""
    async def _run():
        await _create(db, "projects", "p1", {"name": "A"})

        async def attempt(name):
            async with db.session_factory() as session:
                repo = SQLV3ResourceRepository(session)
                result = await repo.update("projects", "p1", {"name": name}, 1)
                await session.commit()
                return result

        results = await asyncio.gather(attempt("B"), attempt("C"))
        successes = [r for r in results if r is not None]
        assert len(successes) == 1, f"expected exactly one CAS winner, got {len(successes)}"
        # The surviving row has version 2.
        final = await _get(db, "projects", "p1")
        assert final["version"] == 2

    asyncio.run(_run())


def test_idempotency_durable_across_new_session(db):
    """A resource created under an idempotency key is found in a new session."""
    async def _run():
        first = await _create(db, "projects", "p1", {"name": "A"}, idem="idem-1")
        assert first["version"] == 1
        # New session, same DB file: idempotency lookup returns the same row.
        async with db.session_factory() as session:
            repo = SQLV3ResourceRepository(session)
            found = await repo.find_by_idempotency("projects", "idem-1")
            assert found is not None
            assert found["name"] == "A"
        # Duplicate create with the same key returns the existing row, not a 500.
        dup = await _create(db, "projects", "p2", {"name": "B"}, idem="idem-1")
        assert dup["name"] == "A"
        assert dup["version"] == 1

    asyncio.run(_run())


def test_idempotency_durable_across_new_container(db, tmp_path):
    """Idempotency survives a full container/engine rebuild on the same DB file."""
    async def _run():
        await _create(db, "projects", "p1", {"name": "A"}, idem="idem-1")
        await db.close()

        # Rebuild a brand-new DatabaseManager against the same file.
        db2 = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'repo.db'}")
        try:
            async with db2.session_factory() as session:
                repo = SQLV3ResourceRepository(session)
                found = await repo.find_by_idempotency("projects", "idem-1")
                assert found is not None
                assert found["name"] == "A"
        finally:
            await db2.close()

    asyncio.run(_run())
