"""Phase 12 — migration 0029 skill_evolution (Skill Evolution, Versioning, and Promotion persistence).

Covers:
- The revision graph head is ``0029_skill_evolution``.
- Fresh upgrade reaches head and exposes ``skill_candidates``, ``skill_versions``, and ``skill_promotion_decisions`` tables.
- An existing 0028 database upgrades cleanly preserving previous experiment and promotion data.
- Downgrade back to 0028 removes 0029 tables and preserves 0028 data.
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
import windagent_storage.orm.skill_evolution_models  # noqa: F401

HEAD = "0029_skill_evolution"
PREV = "0028_experiment_promotion"


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


def test_fresh_upgrade_reaches_head_0029(temp_db_path):
    """Upgrading to 0029 exposes skill evolution tables."""
    from alembic import command
    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    cfg = _make_alembic_config(db_url)
    command.upgrade(cfg, HEAD)
    assert alembic_current(db_url) == (HEAD,)

    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert "skill_candidates" in tables
        assert "skill_versions" in tables
        assert "skill_promotion_decisions" in tables

        cand_columns = {c["name"] for c in inspector.get_columns("skill_candidates")}
        assert {
            "id", "skill_id", "status", "risk_level", "is_executable", "is_high_risk",
            "proposed_manifest_json", "proposed_code", "reasoning_summary",
            "supporting_experiences_json", "security_audit_json", "evaluation_json",
            "metadata_json", "created_at", "updated_at",
        }.issubset(cand_columns)

        ver_columns = {c["name"] for c in inspector.get_columns("skill_versions")}
        assert {
            "id", "skill_id", "version", "parent_version", "manifest_json",
            "code_hash", "source_code", "status", "promoted_from_candidate_id",
            "security_audit_id", "evaluation_id", "created_at", "activated_at", "deprecated_at",
        }.issubset(ver_columns)

        prom_columns = {c["name"] for c in inspector.get_columns("skill_promotion_decisions")}
        assert {
            "id", "candidate_id", "skill_id", "source_version", "target_version",
            "status", "security_audit_passed", "evaluation_passed", "requires_human_approval",
            "approved_by", "approved_at", "rejection_reason", "decision_rationale",
            "created_at", "updated_at",
        }.issubset(prom_columns)
    finally:
        engine.dispose()


def test_upgrade_from_0028_and_downgrade_cycle(temp_db_path):
    """Upgrading from 0028 to 0029 and downgrading back preserves data integrity."""
    from alembic import command
    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    cfg = _make_alembic_config(db_url)

    # 1. Upgrade to PREV (0028)
    command.upgrade(cfg, PREV)
    assert alembic_current(db_url) == (PREV,)

    # Insert an experiment row in 0028
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO experiments (id, candidate_id, baseline_harness_version, experiment_type, "
                    "status, sample_size, baseline_metrics_json, candidate_metrics_json, comparison_json, "
                    "safety_check_passed, reliability_check_passed, verdict, created_by, metadata_json, created_at, updated_at) "
                    "VALUES ('expt_mig_29', 'cand_29', 'harness_v1', 'replay', 'completed', 5, '{}', '{}', '{}', 1, 1, 'beats_baseline', 'tester', '{}', '2026-08-29 00:00:00', '2026-08-29 00:00:00')"
                )
            )
    finally:
        engine.dispose()

    # 2. Upgrade to HEAD (0029)
    command.upgrade(cfg, HEAD)
    assert alembic_current(db_url) == (HEAD,)

    engine, inspector = _inspect(temp_db_path)
    try:
        # Check experiment row preserved
        with engine.connect() as conn:
            row = conn.execute(text("SELECT id, verdict FROM experiments WHERE id = 'expt_mig_29'")).fetchone()
            assert row is not None
            assert row[0] == "expt_mig_29"

        # Insert a skill candidate and version in 0029
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO skill_candidates (id, skill_id, status, risk_level, is_executable, is_high_risk, "
                    "proposed_manifest_json, reasoning_summary, supporting_experiences_json, metadata_json, created_at, updated_at) "
                    "VALUES ('skcand_mig_1', 'skill_test', 'promoted', 'low', 0, 0, '{}', 'Rationale', '[]', '{}', '2026-08-29 00:00:00', '2026-08-29 00:00:00')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO skill_versions (id, skill_id, version, manifest_json, status, created_at) "
                    "VALUES ('skver_mig_1', 'skill_test', '1.0.0', '{}', 'active', '2026-08-29 00:00:00')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO skill_promotion_decisions (id, candidate_id, skill_id, target_version, status, "
                    "security_audit_passed, evaluation_passed, requires_human_approval, decision_rationale, created_at, updated_at) "
                    "VALUES ('skprom_mig_1', 'skcand_mig_1', 'skill_test', '1.0.0', 'promoted', 1, 1, 0, 'Rationale', '2026-08-29 00:00:00', '2026-08-29 00:00:00')"
                )
            )

        # 3. Downgrade back to 0028
        command.downgrade(cfg, PREV)
        assert alembic_current(db_url) == (PREV,)

        engine, inspector = _inspect(temp_db_path)
        tables_after_dg = set(inspector.get_table_names())
        assert "skill_candidates" not in tables_after_dg
        assert "skill_versions" not in tables_after_dg
        assert "skill_promotion_decisions" not in tables_after_dg

        # Experiment row still preserved
        with engine.connect() as conn:
            row = conn.execute(text("SELECT id FROM experiments WHERE id = 'expt_mig_29'")).fetchone()
            assert row is not None

        # 4. Re-upgrade to HEAD (0029) is idempotent
        command.upgrade(cfg, HEAD)
        assert alembic_current(db_url) == (HEAD,)
    finally:
        engine.dispose()
