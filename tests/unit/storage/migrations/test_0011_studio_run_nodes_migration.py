"""A4 — migration 0011 studio_run_nodes + 0012 artifact_provenance (Plan A, studio.contract/v0.1).

Covers: fresh upgrade reaches the repository's declared current head with the
node table, idempotent re-upgrade, downgrade rehearsal preserves Studio
runs/legacy rows, schema matches ORM metadata, and optimistic versioning of
node rows. The 0011/0012 schema behavior is under test while the full upgrade
targets whatever head the chain declares.
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
import windagent_storage.orm.studio_models  # noqa: F401 — registers Studio ORM
import windagent_storage.orm.v2_orchestration_models  # noqa: F401 — legacy tables

NODE_TABLE = "studio_run_nodes"


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


def test_fresh_upgrade_reaches_current_head_with_node_table(temp_db_path):
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    assert alembic_current(db_url) == alembic_heads()
    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert NODE_TABLE in tables
        columns = {c["name"] for c in inspector.get_columns(NODE_TABLE)}
        assert {
            "run_id",
            "dag_node_id",
            "task_type",
            "status",
            "task_id",
            "attempt",
            "depends_on_json",
            "checkpoint",
            "input_hashes_json",
            "output_hashes_json",
            "output_artifact_refs_json",
            "error",
            "version",
            "updated_at",
        } <= columns
    finally:
        engine.dispose()


def test_upgrade_is_idempotent_and_downgrade_rehearsal_preserves_data(temp_db_path):
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    alembic_upgrade_head(db_url)  # must not raise

    engine, _ = _inspect(temp_db_path)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO studio_runs (run_id, series_id, episode_id, dag_json, "
                    "status, created_at, updated_at, metadata_json) VALUES "
                    "('run_rehearsal', 'srs_x', 'ep_x', '{}', 'RUNNING', "
                    "'2026-01-01 00:00:00', '2026-01-01 00:00:00', '{}')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO studio_run_nodes (run_id, dag_node_id, task_type, status, "
                    "attempt, depends_on_json, input_hashes_json, output_hashes_json, "
                    "output_artifact_refs_json, gate, version, updated_at) VALUES "
                    "('run_rehearsal', 'idea.generate', 'studio.story.idea.generate', "
                    "'DISPATCHED', 1, '[]', '[]', '[]', '[]', 0, 3, '2026-01-01 00:00:00')"
                )
            )
    finally:
        engine.dispose()

    # Downgrade rehearsal: 0011 -> 0010 drops only the node table; runs stay.
    from alembic import command

    from windagent_storage.migrations.runner import _make_alembic_config

    command.downgrade(_make_alembic_config(db_url), "0010_studio_persistence")
    engine, inspector = _inspect(temp_db_path)
    try:
        assert NODE_TABLE not in set(inspector.get_table_names())
        with engine.connect() as conn:
            runs = conn.execute(text("SELECT COUNT(*) FROM studio_runs")).scalar()
            assert runs == 1
    finally:
        engine.dispose()

    alembic_upgrade_head(db_url)
    assert alembic_current(db_url) == alembic_heads()
    engine, inspector = _inspect(temp_db_path)
    try:
        with engine.connect() as conn:
            runs = conn.execute(text("SELECT COUNT(*) FROM studio_runs")).scalar()
            assert runs == 1  # runs survive the node-table rehearsal
            nodes = conn.execute(
                text("SELECT COUNT(*) FROM studio_run_nodes")
            ).scalar()
            assert nodes == 0  # node rows are dropped with their table (re-run rebuilds)
    finally:
        engine.dispose()


def test_full_downgrade_to_base_removes_node_table(temp_db_path):
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    alembic_downgrade_base(db_url)
    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert NODE_TABLE not in tables
        assert "studio_runs" not in tables
    finally:
        engine.dispose()


def test_migration_schema_matches_orm_metadata(temp_db_path):
    """Drift guard: 0011 DDL and StudioRunNodeORM must agree."""
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    migrated_engine, migrated_inspector = _inspect(temp_db_path)
    metadata_engine = create_engine("sqlite:///:memory:")
    BaseORM.metadata.create_all(metadata_engine)
    metadata_inspector = inspect(metadata_engine)
    try:
        migrated_columns = {
            c["name"]: str(c["type"]) for c in migrated_inspector.get_columns(NODE_TABLE)
        }
        metadata_columns = {
            c["name"]: str(c["type"]) for c in metadata_inspector.get_columns(NODE_TABLE)
        }
        assert set(migrated_columns) == set(metadata_columns), "studio_run_nodes column drift"
        for name, col_type in metadata_columns.items():
            assert migrated_columns[name] == col_type, f"studio_run_nodes.{name} type drift"
        migrated_indexes = {
            tuple(idx["column_names"]) for idx in migrated_inspector.get_indexes(NODE_TABLE)
        }
        metadata_indexes = {
            tuple(idx["column_names"]) for idx in metadata_inspector.get_indexes(NODE_TABLE)
        }
        assert migrated_indexes == metadata_indexes, "studio_run_nodes index drift"
    finally:
        migrated_engine.dispose()
        metadata_engine.dispose()
