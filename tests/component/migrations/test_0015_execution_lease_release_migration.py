"""Phase 5B1 — migration 0015 execution_lease_release (persist lease release timestamp).

Covers: the revision graph head is ``0015_execution_lease_release`` and a fresh
upgrade exposes the nullable ``released_at`` column; an existing 0014 database
containing a lease row upgrades with the row preserved and ``released_at`` NULL;
downgrade back to 0014 removes only ``released_at`` and preserves the row;
re-upgrade restores the column, preserves the row, and repeated upgrade is
idempotent; and the migrated schema matches the ORM metadata.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from windagent_storage.migrations.runner import (
    alembic_current,
    alembic_heads,
    alembic_upgrade_head,
)
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.v2_orchestration_models  # noqa: F401 — registers ExecutionLeaseORM

TABLE = "execution_leases"
# HEAD was 0015 when this test was written; live_record migration (0019) is now head.
# The test still validates 0015's leased_at semantics, but head is 0019.
HEAD = "0019_live_record_domain"
PREV = "0014_route_lock_authority"


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


def _seed_parent_graph(conn, task_id: str, run_id: str, step_run_id: str) -> None:
    """Seed the task_runs -> v2_workflow_runs_v2 -> workflow_step_runs graph that
    ``execution_leases.step_run_id`` references, using real SQL valid at 0014."""
    conn.execute(
        text(
            "INSERT INTO task_runs (id, session_id, state, version, priority, current_step, "
            "total_steps, pending_permission, retry_count, facts_json, created_at, updated_at) "
            "VALUES (:task_id, 'sess-graph', 'running', 1, 2, 0, 0, 0, 0, '{}', "
            "'2026-08-20 00:00:00', '2026-08-20 00:00:00')"
        ),
        {"task_id": task_id},
    )
    conn.execute(
        text(
            "INSERT INTO v2_workflow_runs_v2 (run_id, workflow_id, session_id, task_run_id, "
            "state, version, checkpoint_cursor, definition_json, created_at, updated_at) "
            "VALUES (:run_id, :run_id, 'sess-graph', :task_id, 'running', 1, 0, '{}', "
            "'2026-08-20 00:00:00', '2026-08-20 00:00:00')"
        ),
        {"run_id": run_id, "task_id": task_id},
    )
    conn.execute(
        text(
            "INSERT INTO workflow_step_runs (id, workflow_run_id, step_order, name, tool_name, "
            "state, priority, updated_at) VALUES (:step_run_id, :run_id, 1, :step_run_id, "
            "'read_file', 'running', 2, '2026-08-20 00:00:00')"
        ),
        {"step_run_id": step_run_id, "run_id": run_id},
    )


def _insert_lease(conn, lease_id: str, step_run_id: str, task_id: str, *, released_at: str | None) -> None:
    """Insert an execution_leases row (0014 shape when released_at is None)."""
    if released_at is None:
        conn.execute(
            text(
                "INSERT INTO execution_leases (lease_id, step_run_id, run_id, worker_id, "
                "status, expires_at, idempotency_key, lease_generation, fencing_token, "
                "created_at, updated_at) VALUES (:lease_id, :step_run_id, :task_id, "
                "'wkr-graph', 'active', '2026-08-20 00:00:00', :idem, 1, 'fence-graph', "
                "'2026-08-20 00:00:00', '2026-08-20 00:00:00')"
            ),
            {"lease_id": lease_id, "step_run_id": step_run_id, "task_id": task_id, "idem": f"idem-{lease_id}"},
        )
    else:
        conn.execute(
            text(
                "INSERT INTO execution_leases (lease_id, step_run_id, run_id, worker_id, "
                "status, expires_at, idempotency_key, lease_generation, fencing_token, "
                "released_at, created_at, updated_at) VALUES (:lease_id, :step_run_id, "
                ":task_id, 'wkr-graph', 'completed', '2026-08-20 00:00:00', :idem, 1, "
                "'fence-graph', :released_at, '2026-08-20 00:00:00', '2026-08-20 01:00:00')"
            ),
            {
                "lease_id": lease_id,
                "step_run_id": step_run_id,
                "task_id": task_id,
                "idem": f"idem-{lease_id}",
                "released_at": released_at,
            },
        )


def test_fresh_upgrade_reaches_head_with_released_at(temp_db_path):
    """The revision graph head is 0015 and a fresh upgrade exposes released_at."""
    assert alembic_heads() == (HEAD,)
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    assert alembic_current(db_url) == (HEAD,)
    engine, inspector = _inspect(temp_db_path)
    try:
        columns = {c["name"] for c in inspector.get_columns(TABLE)}
        assert "released_at" in columns
    finally:
        engine.dispose()


def test_upgrade_from_0014_preserves_lease_row_with_null_released_at(temp_db_path):
    """An existing 0014 DB with a lease row upgrades: row survives, released_at NULL."""
    from alembic import command

    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    command.upgrade(_make_alembic_config(db_url), PREV)
    assert alembic_current(db_url) == (PREV,)

    # Simulate the pre-0015 schema: the 0001 baseline may already have created
    # released_at via metadata create_all, so drop it, then seed the parent
    # graph and a lease row that must survive the upgrade.
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE execution_leases DROP COLUMN released_at"))
            _seed_parent_graph(conn, "task-keep-1", "wf-keep-1", "step-keep-1")
            _insert_lease(conn, "lease-keep-1", "step-keep-1", "task-keep-1", released_at=None)
    finally:
        engine.dispose()

    alembic_upgrade_head(db_url)
    assert alembic_current(db_url) == (HEAD,)

    engine, inspector = _inspect(temp_db_path)
    try:
        columns = {c["name"] for c in inspector.get_columns(TABLE)}
        assert "released_at" in columns
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT lease_id, status, released_at FROM execution_leases "
                    "WHERE lease_id = 'lease-keep-1'"
                )
            ).fetchone()
            assert row is not None
            assert row[1] == "active"
            assert row[2] is None
    finally:
        engine.dispose()


def test_downgrade_to_0014_removes_only_released_at_and_preserves_row(temp_db_path):
    """Downgrading 0015 removes only released_at; the lease row survives."""
    from alembic import command

    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    assert alembic_current(db_url) == (HEAD,)

    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            _seed_parent_graph(conn, "task-keep-2", "wf-keep-2", "step-keep-2")
            _insert_lease(conn, "lease-keep-2", "step-keep-2", "task-keep-2", released_at="2026-08-20 01:00:00")
    finally:
        engine.dispose()

    command.downgrade(_make_alembic_config(db_url), PREV)
    assert alembic_current(db_url) == (PREV,)

    engine, inspector = _inspect(temp_db_path)
    try:
        columns = {c["name"] for c in inspector.get_columns(TABLE)}
        assert "released_at" not in columns
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT lease_id, status FROM execution_leases "
                    "WHERE lease_id = 'lease-keep-2'"
                )
            ).fetchone()
            assert row is not None
            assert row[1] == "completed"
    finally:
        engine.dispose()


def test_reupgrade_restores_column_preserves_row_and_is_idempotent(temp_db_path):
    """Re-upgrade restores released_at, preserves the row, and is idempotent."""
    from alembic import command

    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    assert alembic_current(db_url) == (HEAD,)

    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            _seed_parent_graph(conn, "task-keep-3", "wf-keep-3", "step-keep-3")
            _insert_lease(conn, "lease-keep-3", "step-keep-3", "task-keep-3", released_at="2026-08-20 01:00:00")
    finally:
        engine.dispose()

    command.downgrade(_make_alembic_config(db_url), PREV)
    assert alembic_current(db_url) == (PREV,)

    alembic_upgrade_head(db_url)
    alembic_upgrade_head(db_url)  # repeated upgrade must not raise
    assert alembic_current(db_url) == (HEAD,)

    engine, inspector = _inspect(temp_db_path)
    try:
        columns = {c["name"] for c in inspector.get_columns(TABLE)}
        assert "released_at" in columns
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT lease_id, status, released_at FROM execution_leases "
                    "WHERE lease_id = 'lease-keep-3'"
                )
            ).fetchone()
            assert row is not None
            assert row[1] == "completed"
            # The column was dropped and re-added, so the value is NULL again.
            assert row[2] is None
    finally:
        engine.dispose()


def test_migration_schema_matches_orm_metadata(temp_db_path):
    """Drift guard: 0015 DDL and ExecutionLeaseORM must agree."""
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
        assert set(migrated_columns) == set(metadata_columns), "execution_leases column drift"
        for name, col_type in metadata_columns.items():
            assert migrated_columns[name] == col_type, f"execution_leases.{name} type drift"
        migrated_indexes = {
            tuple(idx["column_names"]) for idx in migrated_inspector.get_indexes(TABLE)
        }
        metadata_indexes = {
            tuple(idx["column_names"]) for idx in metadata_inspector.get_indexes(TABLE)
        }
        assert migrated_indexes == metadata_indexes, "execution_leases index drift"
    finally:
        migrated_engine.dispose()
        metadata_engine.dispose()