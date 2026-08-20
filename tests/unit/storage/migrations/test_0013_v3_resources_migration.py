"""Phase 4 — migration 0013 v3_resources (namespaced durable V3 authority).

Covers: fresh upgrade reaches the head with the v3_resources table, an
existing file DB upgrades to the head and can use the resource repository,
unique (namespace, resource_id) and (namespace, idempotency_key) constraints
are enforced, downgrade removes the table, the migration DDL matches the ORM
metadata, and the 0014 route-lock authority revision upgrades an existing 0013
database (adding the ``route_locks_v3`` columns/index) with data preserved.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from windagent_storage.migrations.runner import (
    alembic_current,
    alembic_downgrade_base,
    alembic_heads,
    alembic_upgrade_head,
)
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.v3_models  # noqa: F401 — registers V3ResourceORM

TABLE = "v3_resources"
ROUTE_LOCKS_TABLE = "route_locks_v3"
DECLARED_HEADS = alembic_heads()


@pytest.fixture
def temp_db_path() -> Path:
    import tempfile

    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    path = Path(handle.name)
    yield path
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        pass


def _inspect(path: Path):
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    inspector = inspect(engine)
    return engine, inspector


def test_fresh_upgrade_reaches_head_with_v3_resources(temp_db_path):
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    assert alembic_current(db_url) == DECLARED_HEADS
    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert TABLE in tables
        columns = {c["name"] for c in inspector.get_columns(TABLE)}
        assert {
            "id",
            "namespace",
            "resource_id",
            "data_json",
            "version",
            "idempotency_key",
            "created_at",
            "updated_at",
        } <= columns
    finally:
        engine.dispose()


def test_existing_file_db_upgrades_to_head_and_uses_repository(temp_db_path):
    """An existing file DB (stamped at 0012) upgrades to 0013 and the resource
    repository can read/write through it."""
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    # Build a DB at the previous head (0012) first. The 0001 baseline uses
    # metadata create_all, so v3_resources may already be materialized; the
    # 0013 migration must still upgrade cleanly (if_not_exists) and the
    # repository must work against the upgraded DB.
    from alembic import command

    from windagent_storage.migrations.runner import _make_alembic_config

    command.upgrade(_make_alembic_config(db_url), "0012_studio_artifact_provenance")
    assert alembic_current(db_url) == ("0012_studio_artifact_provenance",)

    # Upgrade to the new head.
    alembic_upgrade_head(db_url)
    assert alembic_current(db_url) == DECLARED_HEADS

    # The repository can now be used against the upgraded DB.
    import asyncio

    from windagent_storage.database.connection import DatabaseManager
    from windagent_storage.repositories.v3_resource_repository import (
        SQLV3ResourceRepository,
    )

    async def _use_repo() -> None:
        db = DatabaseManager(f"sqlite+aiosqlite:///{temp_db_path.as_posix()}")
        try:
            async with db.session_factory() as session:
                repo = SQLV3ResourceRepository(session)
                created = await repo.create("projects", "proj-1", {"name": "A"})
                assert created["version"] == 1
                await session.commit()
            async with db.session_factory() as session:
                repo = SQLV3ResourceRepository(session)
                got = await repo.get("projects", "proj-1")
                assert got is not None
                assert got["name"] == "A"
        finally:
            await db.close()

    asyncio.run(_use_repo())


def test_fresh_head_route_locks_v3_matches_orm_columns(temp_db_path):
    """Fresh upgrade head materializes the route_locks_v3 authority columns."""
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    assert alembic_current(db_url) == DECLARED_HEADS
    engine, inspector = _inspect(temp_db_path)
    try:
        columns = {c["name"] for c in inspector.get_columns(ROUTE_LOCKS_TABLE)}
        assert {"version", "reselection_reason", "updated_at"} <= columns
        indexes = {ix["name"] for ix in inspector.get_indexes(ROUTE_LOCKS_TABLE)}
        assert "uq_route_locks_v3_active_scope" in indexes
    finally:
        engine.dispose()


def test_upgrade_from_0013_adds_route_lock_authority_columns(temp_db_path):
    """An existing 0013 DB missing the route_locks_v3 authority columns is
    upgraded by 0014 with data preserved."""
    from alembic import command

    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    command.upgrade(_make_alembic_config(db_url), "0013_v3_resources")
    assert alembic_current(db_url) == ("0013_v3_resources",)

    # Simulate the pre-0014 schema: drop the authority columns/index that the
    # old ad-hoc migration used to add outside the Alembic chain, and keep an
    # existing lock row that must survive the upgrade.
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP INDEX IF EXISTS uq_route_locks_v3_active_scope"))
            conn.execute(text("ALTER TABLE route_locks_v3 DROP COLUMN version"))
            conn.execute(text("ALTER TABLE route_locks_v3 DROP COLUMN reselection_reason"))
            conn.execute(text("ALTER TABLE route_locks_v3 DROP COLUMN updated_at"))
            conn.execute(text(
                "INSERT INTO route_locks_v3 (id, scope_type, scope_id, canonical_model_id, "
                "policy_version, routing_snapshot_json, status, created_at) VALUES "
                "('lock-keep-1', 'session', 's1', 'anthropic/claude-3-5-sonnet', 1, '{}', "
                "'active', CURRENT_TIMESTAMP)"
            ))
    finally:
        engine.dispose()

    # Upgrade to the new head: 0014 re-adds the columns/index, preserving rows.
    alembic_upgrade_head(db_url)
    assert alembic_current(db_url) == DECLARED_HEADS

    engine, inspector = _inspect(temp_db_path)
    try:
        columns = {c["name"] for c in inspector.get_columns(ROUTE_LOCKS_TABLE)}
        assert {"version", "reselection_reason", "updated_at"} <= columns
        indexes = {ix["name"] for ix in inspector.get_indexes(ROUTE_LOCKS_TABLE)}
        assert "uq_route_locks_v3_active_scope" in indexes
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT id, status FROM route_locks_v3 WHERE id = 'lock-keep-1'"
            )).fetchone()
            assert row is not None
            assert row[1] == "active"
    finally:
        engine.dispose()


def test_unique_namespace_resource_id_enforced(temp_db_path):
    from sqlalchemy.exc import IntegrityError

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO v3_resources (namespace, resource_id, data_json, version, "
                "created_at, updated_at) VALUES ('projects', 'p1', '{}', 1, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO v3_resources (namespace, resource_id, data_json, version, "
                    "created_at, updated_at) VALUES ('projects', 'p1', '{}', 1, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ))
    finally:
        engine.dispose()


def test_unique_namespace_idempotency_key_enforced(temp_db_path):
    from sqlalchemy.exc import IntegrityError

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO v3_resources (namespace, resource_id, data_json, version, "
                "idempotency_key, created_at, updated_at) VALUES ('projects', 'p1', '{}', 1, "
                "'idem-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO v3_resources (namespace, resource_id, data_json, version, "
                    "idempotency_key, created_at, updated_at) VALUES ('projects', 'p2', '{}', 1, "
                    "'idem-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ))
        # Same idempotency key in a different namespace is allowed.
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO v3_resources (namespace, resource_id, data_json, version, "
                "idempotency_key, created_at, updated_at) VALUES ('episodes', 'e1', '{}', 1, "
                "'idem-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
    finally:
        engine.dispose()


def test_downgrade_removes_v3_resources(temp_db_path):
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    alembic_downgrade_base(db_url)
    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert TABLE not in tables
    finally:
        engine.dispose()


def test_downgrade_0014_removes_route_lock_authority_columns(temp_db_path):
    """Downgrading 0014 removes only the route-lock authority columns/index."""
    from alembic import command

    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    assert alembic_current(db_url) == DECLARED_HEADS

    command.downgrade(_make_alembic_config(db_url), "0013_v3_resources")
    assert alembic_current(db_url) == ("0013_v3_resources",)

    engine, inspector = _inspect(temp_db_path)
    try:
        columns = {c["name"] for c in inspector.get_columns(ROUTE_LOCKS_TABLE)}
        assert "version" not in columns
        assert "reselection_reason" not in columns
        assert "updated_at" not in columns
        indexes = {ix["name"] for ix in inspector.get_indexes(ROUTE_LOCKS_TABLE)}
        assert "uq_route_locks_v3_active_scope" not in indexes
    finally:
        engine.dispose()


def test_migration_schema_matches_orm_metadata(temp_db_path):
    """Drift guard: 0013 DDL and V3ResourceORM must agree."""
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    migrated_engine, migrated_inspector = _inspect(temp_db_path)
    metadata_engine = create_engine("sqlite:///:memory:")
    BaseORM.metadata.create_all(metadata_engine)
    metadata_inspector = inspect(metadata_engine)
    try:
        migrated_columns = {
            c["name"]: str(c["type"]) for c in migrated_inspector.get_columns(TABLE)
        }
        metadata_columns = {
            c["name"]: str(c["type"]) for c in metadata_inspector.get_columns(TABLE)
        }
        assert set(migrated_columns) == set(metadata_columns), "v3_resources column drift"
        for name, col_type in metadata_columns.items():
            assert migrated_columns[name] == col_type, f"v3_resources.{name} type drift"
        migrated_indexes = {
            tuple(idx["column_names"]) for idx in migrated_inspector.get_indexes(TABLE)
        }
        metadata_indexes = {
            tuple(idx["column_names"]) for idx in metadata_inspector.get_indexes(TABLE)
        }
        assert migrated_indexes == metadata_indexes, "v3_resources index drift"
    finally:
        migrated_engine.dispose()
        metadata_engine.dispose()
