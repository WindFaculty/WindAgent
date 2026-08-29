"""Phase 10 — migration 0027 continual_harness (HarnessVersion and RefinementProposal persistence).

Covers:
- The revision graph head is ``0027_continual_harness``.
- Fresh upgrade reaches head and exposes ``harness_versions`` and ``refinement_proposals`` tables.
- An existing 0026 database upgrades cleanly preserving previous candidate & rule data.
- Downgrade back to 0026 removes ``harness_versions`` and ``refinement_proposals`` and preserves 0026 data.
- Re-upgrade restores the tables, and repeated upgrade is idempotent.
- The migrated schema matches BaseORM declarative metadata.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from sqlalchemy import create_engine, inspect, text

from windagent_storage.migrations.runner import (
    alembic_current,
    alembic_heads,
    alembic_upgrade_head,
)
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.harness_models  # noqa: F401
import windagent_storage.orm.candidate_models  # noqa: F401

TARGET = "0027_continual_harness"
PREV = "0026_candidate_learning"


@pytest.fixture
def temp_db_path() -> Path:
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


def test_upgrade_creates_0027_tables(temp_db_path):
    """Upgrading to 0027 exposes harness_versions and refinement_proposals."""
    from alembic import command
    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    cfg = _make_alembic_config(db_url)
    command.upgrade(cfg, TARGET)
    assert alembic_current(db_url) == (TARGET,)

    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert "harness_versions" in tables
        assert "refinement_proposals" in tables

        hv_columns = {c["name"] for c in inspector.get_columns("harness_versions")}
        assert {
            "id", "version_number", "parent_version", "status", "entries_json",
            "diff_json", "evidence_json", "promotion_decision_json", "evaluation_set_json",
            "created_by", "project_id", "domain", "is_active", "metadata_json",
            "created_at", "updated_at",
        }.issubset(hv_columns)

        rf_columns = {c["name"] for c in inspector.get_columns("refinement_proposals")}
        assert {
            "id", "target_harness_version", "candidate_ids_json", "proposed_entries_json",
            "preview_diff_json", "status", "evaluation_results_json", "project_id",
            "created_by", "metadata_json", "created_at", "updated_at",
        }.issubset(rf_columns)
    finally:
        engine.dispose()


def test_upgrade_from_0026_and_downgrade_cycle(temp_db_path):
    """Upgrading from 0026 to 0027 and downgrading back preserves data integrity."""
    from alembic import command
    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    cfg = _make_alembic_config(db_url)

    # 1. Upgrade to PREV (0026)
    command.upgrade(cfg, PREV)
    assert alembic_current(db_url) == (PREV,)

    # Insert a candidate row in 0026
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO learning_candidates (id, kind, condition, proposed_change_json, "
                    "reasoning_summary, supporting_experiences_json, counter_evidence_json, "
                    "sample_size, confidence, scope, risk_level, status, metadata_json, created_at, updated_at) "
                    "VALUES ('cand_mig_1', 'prompt_rule', 'cond', '{}', 'summary', '[]', '[]', "
                    "1, 0.8, 'project', 'low', 'proposed', '{}', '2026-08-29 00:00:00', '2026-08-29 00:00:00')"
                )
            )
    finally:
        engine.dispose()

    # 2. Upgrade to TARGET (0027)
    command.upgrade(cfg, TARGET)
    assert alembic_current(db_url) == (TARGET,)

    engine, inspector = _inspect(temp_db_path)
    try:
        # Check candidate row preserved
        with engine.connect() as conn:
            row = conn.execute(text("SELECT id, status FROM learning_candidates WHERE id = 'cand_mig_1'")).fetchone()
            assert row is not None
            assert row[0] == "cand_mig_1"

        # Insert a harness version row in 0027
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO harness_versions (id, version_number, status, entries_json, "
                    "diff_json, evidence_json, promotion_decision_json, evaluation_set_json, "
                    "created_by, is_active, metadata_json, created_at, updated_at) "
                    "VALUES ('harness_mig_1', 1, 'active', '[]', '{}', '[]', '{}', '{}', "
                    "'system', 1, '{}', '2026-08-29 00:00:00', '2026-08-29 00:00:00')"
                )
            )
    finally:
        engine.dispose()

    # 3. Downgrade back to PREV (0026)
    command.downgrade(cfg, PREV)
    assert alembic_current(db_url) == (PREV,)

    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert "harness_versions" not in tables
        assert "refinement_proposals" not in tables
        # 0026 candidate row still preserved
        with engine.connect() as conn:
            row = conn.execute(text("SELECT id FROM learning_candidates WHERE id = 'cand_mig_1'")).fetchone()
            assert row is not None
    finally:
        engine.dispose()

    # 4. Re-upgrade to HEAD (idempotent)
    alembic_upgrade_head(db_url)
    alembic_upgrade_head(db_url)
    assert alembic_current(db_url) == alembic_heads()


def test_migration_schema_matches_orm_metadata(temp_db_path):
    """Drift guard: 0027 DDL and BaseORM declarative metadata must agree."""
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    migrated_engine, migrated_inspector = _inspect(temp_db_path)

    metadata_engine = create_engine("sqlite:///:memory:")
    BaseORM.metadata.create_all(metadata_engine)
    metadata_inspector = inspect(metadata_engine)

    try:
        for table_name in ["harness_versions", "refinement_proposals"]:
            migrated_cols = {c["name"]: str(c["type"]) for c in migrated_inspector.get_columns(table_name)}
            meta_cols = {c["name"]: str(c["type"]) for c in metadata_inspector.get_columns(table_name)}
            assert set(migrated_cols) == set(meta_cols), f"{table_name} column drift"
    finally:
        migrated_engine.dispose()
        metadata_engine.dispose()
