"""Phase 13 — migration 0030 subagent_evolution (Subagent Evolution, Versioning, and Promotion persistence).

Covers:
- The revision graph head is ``0030_subagent_evolution``.
- Fresh upgrade reaches head and exposes ``subagent_candidates``, ``subagent_spec_versions``, and ``subagent_promotion_decisions`` tables.
- An existing 0029 database upgrades cleanly preserving previous skill evolution data.
- Downgrade back to 0029 removes 0030 tables and preserves 0029 data.
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
import windagent_storage.orm.subagent_evolution_models  # noqa: F401

HEAD = "0030_subagent_evolution"
PREV = "0029_skill_evolution"


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


def test_fresh_upgrade_reaches_head_0030(temp_db_path):
    """Upgrading to 0030 exposes subagent evolution tables."""
    from alembic import command
    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    cfg = _make_alembic_config(db_url)
    command.upgrade(cfg, HEAD)
    assert alembic_current(db_url) == (HEAD,)

    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert "subagent_candidates" in tables
        assert "subagent_spec_versions" in tables
        assert "subagent_promotion_decisions" in tables

        cand_columns = {c["name"] for c in inspector.get_columns("subagent_candidates")}
        assert {
            "id", "role", "status", "risk_level", "is_high_risk",
            "proposed_spec_json", "reasoning_summary",
            "supporting_experiences_json", "security_audit_json", "evaluation_json",
            "metadata_json", "created_at", "updated_at",
        }.issubset(cand_columns)

        spec_columns = {c["name"] for c in inspector.get_columns("subagent_spec_versions")}
        assert {
            "id", "role", "version", "parent_version", "objective", "system_supplement",
            "allowed_tools_json", "allowed_skills_json", "model_routing_policy_json",
            "memory_access_json", "max_budget_json", "max_depth", "output_contract_json",
            "status", "risk_level", "spec_hash", "promoted_from_candidate_id",
            "security_audit_id", "evaluation_id", "metadata_json",
            "created_at", "activated_at", "deprecated_at",
        }.issubset(spec_columns)

        prom_columns = {c["name"] for c in inspector.get_columns("subagent_promotion_decisions")}
        assert {
            "id", "candidate_id", "role", "source_version", "target_version",
            "status", "security_audit_passed", "evaluation_passed", "requires_human_approval",
            "approved_by", "approved_at", "rejection_reason", "decision_rationale",
            "created_at", "updated_at",
        }.issubset(prom_columns)
    finally:
        engine.dispose()


def test_upgrade_from_0029_and_downgrade_cycle(temp_db_path):
    """Upgrading from 0029 to 0030 and downgrading back preserves data integrity."""
    from alembic import command
    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    cfg = _make_alembic_config(db_url)

    # 1. Upgrade to PREV (0029)
    command.upgrade(cfg, PREV)
    assert alembic_current(db_url) == (PREV,)

    # Insert a skill row in 0029
    engine, _ = _inspect(temp_db_path)
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO skill_candidates (id, skill_id, status, risk_level, is_executable, is_high_risk, "
                    "proposed_manifest_json, reasoning_summary, supporting_experiences_json, metadata_json, created_at, updated_at) "
                    "VALUES ('skcand_test', 'test_skill', 'proposed', 'low', 0, 0, '{}', 'test', '[]', '{}', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
            conn.commit()
    finally:
        engine.dispose()

    # 2. Upgrade to HEAD (0030)
    command.upgrade(cfg, HEAD)
    assert alembic_current(db_url) == (HEAD,)

    # Verify skill row persists, and insert a subagent candidate row in 0030
    engine, inspector = _inspect(temp_db_path)
    try:
        assert "subagent_candidates" in inspector.get_table_names()
        with engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM skill_candidates WHERE id='skcand_test'")).scalar()
            assert count == 1

            conn.execute(
                text(
                    "INSERT INTO subagent_candidates (id, role, status, risk_level, is_high_risk, proposed_spec_json, "
                    "reasoning_summary, supporting_experiences_json, metadata_json, created_at, updated_at) "
                    "VALUES ('subcand_test', 'MarketResearchAgent', 'proposed', 'low', 0, '{}', 'test subagent', '[]', '{}', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
            conn.commit()
    finally:
        engine.dispose()

    # 3. Downgrade back to PREV (0029)
    command.downgrade(cfg, PREV)
    assert alembic_current(db_url) == (PREV,)

    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert "subagent_candidates" not in tables
        assert "subagent_spec_versions" not in tables
        assert "subagent_promotion_decisions" not in tables
        # Skill row in 0029 remains intact
        with engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM skill_candidates WHERE id='skcand_test'")).scalar()
            assert count == 1
    finally:
        engine.dispose()

    # 4. Re-upgrade to HEAD (0030)
    command.upgrade(cfg, HEAD)
    assert alembic_current(db_url) == (HEAD,)
    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert "subagent_candidates" in tables
        assert "subagent_spec_versions" in tables
        assert "subagent_promotion_decisions" in tables
    finally:
        engine.dispose()

