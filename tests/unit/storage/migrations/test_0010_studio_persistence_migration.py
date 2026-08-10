"""A3 migration tests: 0010_studio_persistence (studio.contract/v0.1).

Covers the STUDIO_PERSISTENCE_GATE migration surface:
- fresh database ``alembic upgrade head`` produces exactly one head and the
  full Studio schema (tables + uniqueness indexes + outbox ordering index),
- a representative legacy fixture (V2 projects/revisions) upgrades through
  the deterministic backfill with no invented story content and identical
  identities on both read paths,
- downgrade rehearsal removes only Studio-owned objects and preserves legacy
  rows; re-upgrade is clean,
- schema drift: the migration DDL matches ``BaseORM.metadata`` for every
  Studio table (columns + unique indexes),
- the outbox ordering index is skipped (with a warning) when legacy outbox
  rows already violate per-aggregate uniqueness, so upgrades never block.
"""

from __future__ import annotations

import json
import tempfile
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
import windagent_storage.orm.studio_models  # noqa: F401  (registers Studio tables on metadata)
import windagent_storage.video_production.video_production_models  # noqa: F401  (legacy tables)
from windagent_storage.studio.backfill import synthetic_episode_id

STUDIO_TABLES = [
    "studio_series_projects",
    "studio_episodes",
    "studio_revisions",
    "studio_artifacts",
    "studio_approval_policies",
    "studio_approval_decisions",
    "studio_runs",
    "studio_events",
]

STUDIO_UNIQUE_INDEXES = [
    "uq_studio_episode_series_number",
    "uq_studio_revision_episode_hash",
    "uq_studio_artifact_hash",
    "uq_studio_approval_revision_checkpoint_actor",
    "uq_studio_event_aggregate_sequence",
]


@pytest.fixture
def temp_db_path():
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    path = Path(handle.name)
    yield path
    # Best-effort cleanup on Windows (engine must be disposed by the test).
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        pass


def _inspect(path: Path):
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        return engine, inspect(engine)
    finally:
        engine.dispose()


def _upgrade_to_legacy_head(path: Path) -> None:
    """Upgrade to the pre-Studio head (0009) so legacy fixture rows exist pre-backfill."""
    from alembic import command
    from windagent_storage.migrations.runner import _make_alembic_config

    command.upgrade(_make_alembic_config(f"sqlite:///{path.as_posix()}"), "0009_immutable_plan_revisions")


def _seed_legacy_fixture(path: Path) -> dict:
    """Insert a representative legacy V2 fixture (projects + revisions)."""
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO video_production_projects "
                "(id, name, status, active_revision_id, created_at, updated_at) VALUES "
                "('proj_legacy_1', 'Legacy Pilot', 'ACTIVE', 'rev_legacy_2', "
                "'2026-01-01 00:00:00', '2026-01-02 00:00:00'), "
                "('proj_legacy_2', 'Second Show', 'DRAFT', '', "
                "'2026-02-01 00:00:00', '2026-02-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO video_production_revisions "
                "(id, project_id, parent_revision_id, status, content_hash, sequence, created_at) VALUES "
                "('rev_legacy_1', 'proj_legacy_1', NULL, 'DRAFT', "
                "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 0, "
                "'2026-01-01 08:00:00'), "
                "('rev_legacy_2', 'proj_legacy_1', 'rev_legacy_1', 'LOCKED', "
                "'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 1, "
                "'2026-01-01 09:00:00'), "
                "('rev_legacy_3', 'proj_legacy_2', NULL, 'DRAFT', '', 0, '2026-02-01 09:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO v2_outbox_records "
                "(id, event_id, aggregate_id, aggregate_type, event_type, payload_json, "
                "schema_version, sequence_number, attempt_count, created_at, available_at, status) VALUES "
                "('out_1', 'evt_1', 'agg_legacy', 'test', 'legacy.event', '{}', 1, 3, 0, "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00', 'pending'), "
                "('out_2', 'evt_2', 'agg_legacy', 'test', 'legacy.event', '{}', 1, 3, 0, "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00', 'pending')"
            )
        )
    engine.dispose()
    return {
        "projects": 2,
        "revisions": 3,
        "episodes": 2,
        "series": 2,
    }


def test_single_head_and_fresh_upgrade_creates_full_studio_schema(temp_db_path):
    assert alembic_heads() == ("0010_studio_persistence",)
    alembic_upgrade_head(f"sqlite:///{temp_db_path.as_posix()}")
    assert alembic_current(f"sqlite:///{temp_db_path.as_posix()}") == ("0010_studio_persistence",)

    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert STUDIO_TABLES == [t for t in STUDIO_TABLES if t in tables] and all(
            t in tables for t in STUDIO_TABLES
        )
        index_names = set()
        for table in STUDIO_TABLES:
            index_names |= {idx["name"] for idx in inspector.get_indexes(table)}
        for unique_index in STUDIO_UNIQUE_INDEXES:
            assert unique_index in index_names, unique_index
        outbox_indexes = {idx["name"] for idx in inspector.get_indexes("v2_outbox_records")}
        assert "uq_v2_outbox_aggregate_sequence" in outbox_indexes
    finally:
        engine.dispose()


def test_legacy_fixture_upgrade_backfills_deterministically(temp_db_path):
    _upgrade_to_legacy_head(temp_db_path)
    expected = _seed_legacy_fixture(temp_db_path)
    alembic_upgrade_head(f"sqlite:///{temp_db_path.as_posix()}")

    engine, _ = _inspect(temp_db_path)
    try:
        with engine.connect() as conn:
            series = conn.execute(text("SELECT series_id, title, metadata_json FROM studio_series_projects")).fetchall()
            assert len(series) == expected["series"]
            by_id = {s.series_id: s for s in series}
            assert by_id["proj_legacy_1"].title == "Legacy Pilot"
            meta1 = json.loads(by_id["proj_legacy_1"].metadata_json)
            assert meta1["backfilled"] is True
            assert meta1["legacy_project_status"] == "ACTIVE"
            assert meta1["legacy_active_revision_id"] == "rev_legacy_2"
            assert "story" not in json.dumps(meta1).lower()  # structural only

            episodes = conn.execute(text("SELECT episode_id, series_id, title, state FROM studio_episodes")).fetchall()
            assert len(episodes) == expected["episodes"]
            for ep in episodes:
                assert ep.episode_id == synthetic_episode_id(ep.series_id)
                assert ep.state == "DRAFT"
                assert ep.series_id in {"proj_legacy_1", "proj_legacy_2"}

            revisions = conn.execute(
                text("SELECT revision_id, episode_id, content_hash, status, lock_state, metadata_json "
                     "FROM studio_revisions ORDER BY revision_id")
            ).fetchall()
            assert len(revisions) == expected["revisions"]
            rev_by_id = {r.revision_id: r for r in revisions}
            # real legacy hash preserved for rev_legacy_1/2
            assert rev_by_id["rev_legacy_1"].content_hash == "a" * 64
            assert rev_by_id["rev_legacy_2"].content_hash == "b" * 64
            assert rev_by_id["rev_legacy_2"].status == "LOCKED"
            assert rev_by_id["rev_legacy_2"].lock_state == "LOCKED"
            # empty legacy hash -> deterministic structural hash, marked
            meta3 = json.loads(rev_by_id["rev_legacy_3"].metadata_json)
            assert meta3["hash_backfilled"] is True
            assert len(rev_by_id["rev_legacy_3"].content_hash) == 64
            # episode binding is deterministic
            assert rev_by_id["rev_legacy_1"].episode_id == synthetic_episode_id("proj_legacy_1")

            # outbox rows untouched by backfill
            outbox = conn.execute(text("SELECT COUNT(*) FROM v2_outbox_records")).scalar()
            assert outbox == 2
    finally:
        engine.dispose()


def test_downgrade_rehearsal_preserves_legacy_and_reupgrades(temp_db_path):
    _upgrade_to_legacy_head(temp_db_path)
    _seed_legacy_fixture(temp_db_path)
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)

    from alembic import command
    from windagent_storage.migrations.runner import _make_alembic_config

    command.downgrade(_make_alembic_config(db_url), "0009_immutable_plan_revisions")

    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert not any(t.startswith("studio_") for t in tables)
        outbox_indexes = {idx["name"] for idx in inspector.get_indexes("v2_outbox_records")}
        assert "uq_v2_outbox_aggregate_sequence" not in outbox_indexes
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM video_production_projects")).scalar() == 2
            assert conn.execute(text("SELECT COUNT(*) FROM video_production_revisions")).scalar() == 3
            assert conn.execute(text("SELECT COUNT(*) FROM v2_outbox_records")).scalar() == 2
    finally:
        engine.dispose()

    # re-upgrade after rehearsal is clean
    alembic_upgrade_head(db_url)
    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert all(t in tables for t in STUDIO_TABLES)
    finally:
        engine.dispose()


def test_outbox_ordering_index_skipped_when_legacy_duplicates_exist(temp_db_path):
    _upgrade_to_legacy_head(temp_db_path)
    _seed_legacy_fixture(temp_db_path)  # contains duplicate (agg_legacy, 3)
    alembic_upgrade_head(f"sqlite:///{temp_db_path.as_posix()}")  # must not raise

    engine, inspector = _inspect(temp_db_path)
    try:
        outbox_indexes = {idx["name"] for idx in inspector.get_indexes("v2_outbox_records")}
        assert "uq_v2_outbox_aggregate_sequence" not in outbox_indexes
        assert all(t in inspector.get_table_names() for t in STUDIO_TABLES)
    finally:
        engine.dispose()


def test_migration_schema_matches_orm_metadata(temp_db_path):
    """Drift guard: 0010 DDL and BaseORM.metadata must agree for Studio tables."""
    alembic_upgrade_head(f"sqlite:///{temp_db_path.as_posix()}")
    migrated_engine, migrated_inspector = _inspect(temp_db_path)

    metadata_engine = create_engine("sqlite:///:memory:")
    BaseORM.metadata.create_all(metadata_engine)
    metadata_inspector = inspect(metadata_engine)
    try:
        for table in STUDIO_TABLES:
            migrated_columns = {
                c["name"]: str(c["type"]) for c in migrated_inspector.get_columns(table)
            }
            metadata_columns = {
                c["name"]: str(c["type"]) for c in metadata_inspector.get_columns(table)
            }
            assert set(migrated_columns) == set(metadata_columns), f"{table} column drift"
            for name, col_type in metadata_columns.items():
                assert migrated_columns[name] == col_type, f"{table}.{name} type drift"

        migrated_indexes = {}
        metadata_indexes = {}
        for table in STUDIO_TABLES:
            # SQLite names UniqueConstraint indexes sqlite_autoindex_*; compare
            # unique column tuples so naming conventions cannot mask drift.
            migrated_indexes[table] = {
                tuple(idx["column_names"])
                for idx in migrated_inspector.get_indexes(table, include_auto_indexes=True)
                if idx["unique"]
            }
            metadata_indexes[table] = {
                tuple(idx["column_names"])
                for idx in metadata_inspector.get_indexes(table, include_auto_indexes=True)
                if idx["unique"]
            }
            assert migrated_indexes[table] == metadata_indexes[table], f"{table} unique-index drift"
    finally:
        migrated_engine.dispose()
        metadata_engine.dispose()


def test_full_downgrade_to_base_removes_studio_tables(temp_db_path):
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    alembic_downgrade_base(db_url)
    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert not any(t.startswith("studio_") for t in tables)
        assert "alembic_version" in tables  # alembic manages its stamp table
    finally:
        engine.dispose()
