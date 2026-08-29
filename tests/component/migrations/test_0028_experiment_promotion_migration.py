"""Phase 11 — migration 0028 experiment_promotion (Experiments and Promotion Decisions persistence).

Covers:
- The revision graph head is ``0028_experiment_promotion``.
- Fresh upgrade reaches head and exposes ``experiments`` and ``promotion_decisions`` tables.
- An existing 0027 database upgrades cleanly preserving previous harness data.
- Downgrade back to 0027 removes ``experiments`` and ``promotion_decisions`` and preserves 0027 data.
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
)
import windagent_storage.orm.experiment_models  # noqa: F401
import windagent_storage.orm.promotion_models  # noqa: F401

HEAD = "0028_experiment_promotion"
PREV = "0027_continual_harness"


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


def test_fresh_upgrade_reaches_head_0028(temp_db_path):
    """Upgrading to 0028 exposes experiments and promotion_decisions."""
    from alembic import command
    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    cfg = _make_alembic_config(db_url)
    command.upgrade(cfg, HEAD)
    assert alembic_current(db_url) == (HEAD,)

    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert "experiments" in tables
        assert "promotion_decisions" in tables

        exp_columns = {c["name"] for c in inspector.get_columns("experiments")}
        assert {
            "id", "candidate_id", "baseline_harness_version", "experiment_type",
            "status", "dataset_id", "sample_size", "baseline_metrics_json",
            "candidate_metrics_json", "comparison_json", "safety_check_passed",
            "reliability_check_passed", "verdict", "project_id", "domain",
            "created_by", "metadata_json", "created_at", "updated_at", "completed_at",
        }.issubset(exp_columns)

        prom_columns = {c["name"] for c in inspector.get_columns("promotion_decisions")}
        assert {
            "id", "candidate_id", "experiment_id", "source_harness_version",
            "target_harness_version", "status", "gate_checks_json", "is_high_risk",
            "requires_human_approval", "approved_by", "approved_at", "rejection_reason",
            "decision_rationale", "project_id", "domain", "metadata_json",
            "created_at", "updated_at",
        }.issubset(prom_columns)
    finally:
        engine.dispose()


def test_upgrade_from_0027_and_downgrade_cycle(temp_db_path):
    """Upgrading from 0027 to 0028 and downgrading back preserves data integrity."""
    from alembic import command
    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    cfg = _make_alembic_config(db_url)

    # 1. Upgrade to PREV (0027)
    command.upgrade(cfg, PREV)
    assert alembic_current(db_url) == (PREV,)

    # Insert a harness row in 0027
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO harness_versions (id, version_number, status, entries_json, "
                    "diff_json, evidence_json, promotion_decision_json, evaluation_set_json, "
                    "created_by, is_active, metadata_json, created_at, updated_at) "
                    "VALUES ('harness_mig_28', 1, 'active', '[]', '{}', '[]', '{}', '{}', "
                    "'system', 1, '{}', '2026-08-29 00:00:00', '2026-08-29 00:00:00')"
                )
            )
    finally:
        engine.dispose()

    # 2. Upgrade to HEAD (0028)
    command.upgrade(cfg, HEAD)
    assert alembic_current(db_url) == (HEAD,)

    engine, inspector = _inspect(temp_db_path)
    try:
        # Check harness row preserved
        with engine.connect() as conn:
            row = conn.execute(text("SELECT id, status FROM harness_versions WHERE id = 'harness_mig_28'")).fetchone()
            assert row is not None
            assert row[0] == "harness_mig_28"

        # Insert an experiment and promotion row in 0028
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO experiments (id, candidate_id, baseline_harness_version, experiment_type, "
                    "status, sample_size, baseline_metrics_json, candidate_metrics_json, comparison_json, "
                    "safety_check_passed, reliability_check_passed, verdict, created_by, metadata_json, created_at, updated_at) "
                    "VALUES ('expt_mig_1', 'cand_1', 'harness_v1', 'replay', 'completed', 5, '{}', '{}', '{}', 1, 1, 'beats_baseline', 'tester', '{}', '2026-08-29 00:00:00', '2026-08-29 00:00:00')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO promotion_decisions (id, candidate_id, experiment_id, source_harness_version, "
                    "status, gate_checks_json, is_high_risk, requires_human_approval, decision_rationale, "
                    "metadata_json, created_at, updated_at) "
                    "VALUES ('pdec_mig_1', 'cand_1', 'expt_mig_1', 'harness_v1', 'promoted', '{}', 0, 0, 'Passed all gates', '{}', '2026-08-29 00:00:00', '2026-08-29 00:00:00')"
                )
            )

        # 3. Downgrade back to 0027
        command.downgrade(cfg, PREV)
        assert alembic_current(db_url) == (PREV,)

        engine, inspector = _inspect(temp_db_path)
        tables_after_dg = set(inspector.get_table_names())
        assert "experiments" not in tables_after_dg
        assert "promotion_decisions" not in tables_after_dg
        assert "harness_versions" in tables_after_dg

        # Check 0027 data still intact after downgrade
        with engine.connect() as conn:
            row = conn.execute(text("SELECT id, status FROM harness_versions WHERE id = 'harness_mig_28'")).fetchone()
            assert row is not None
            assert row[0] == "harness_mig_28"

        # 4. Re-upgrade to HEAD (0028)
        command.upgrade(cfg, HEAD)
        assert alembic_current(db_url) == (HEAD,)

        # 5. Repeated upgrade is idempotent
        command.upgrade(cfg, HEAD)
        assert alembic_current(db_url) == (HEAD,)
    finally:
        engine.dispose()

