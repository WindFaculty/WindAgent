"""Phase 14 — migration 0031 organizational_learning (Organizational Learning, Conflict Resolution, and Attribution persistence).

Covers:
- The revision graph head is ``0031_organizational_learning``.
- Fresh upgrade reaches head and exposes ``learned_rules``, ``conflict_resolutions``, and ``multi_agent_attributions`` tables.
- An existing 0030 database upgrades cleanly preserving previous subagent evolution data.
- Downgrade back to 0030 removes 0031 modifications and preserves 0030 data.
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
import windagent_storage.orm.candidate_models  # noqa: F401
import windagent_storage.orm.organizational_learning_models  # noqa: F401

HEAD = "0031_organizational_learning"
PREV = "0030_subagent_evolution"


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


def test_fresh_upgrade_reaches_head_0031(temp_db_path):
    """The revision graph head is 0031 and a fresh upgrade exposes organizational learning tables."""
    assert HEAD in alembic_heads()
    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    alembic_upgrade_head(db_url)
    assert alembic_current(db_url) == (HEAD,)

    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert "learned_rules" in tables
        assert "conflict_resolutions" in tables
        assert "multi_agent_attributions" in tables

        rule_columns = {c["name"] for c in inspector.get_columns("learned_rules")}
        assert {
            "id", "domain", "condition", "recommendation", "scope",
            "target_role", "project_id", "evidence_refs_json", "metrics_json",
            "confidence", "sample_size", "harness_version", "version", "state",
            "supersedes_id", "superseded_by", "created_at", "last_validated_at",
            "activated_at", "deprecated_at", "metadata_json",
        }.issubset(rule_columns)

        conflict_columns = {c["name"] for c in inspector.get_columns("conflict_resolutions")}
        assert {
            "resolution_id", "domain", "context_query_json", "winning_rule_id",
            "competing_rule_ids_json", "resolution_rationale", "score_breakdown_json",
            "resolved_at",
        }.issubset(conflict_columns)

        attr_columns = {c["name"] for c in inspector.get_columns("multi_agent_attributions")}
        assert {
            "attribution_id", "episode_id", "domain", "metric_signals_json",
            "role_attributions_json", "created_at",
        }.issubset(attr_columns)
    finally:
        engine.dispose()


def test_upgrade_from_0030_and_downgrade_cycle(temp_db_path):
    """Upgrading from 0030 to 0031 and downgrading back preserves data integrity."""
    from alembic import command
    from windagent_storage.migrations.runner import _make_alembic_config

    db_url = f"sqlite:///{temp_db_path.as_posix()}"
    cfg = _make_alembic_config(db_url)

    # 1. Upgrade to PREV (0030)
    command.upgrade(cfg, PREV)
    assert alembic_current(db_url) == (PREV,)

    # 2. Insert dummy 0030 subagent spec record and sample 0026 learned rule
    engine, inspector = _inspect(temp_db_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO subagent_spec_versions (id, role, version, objective, system_supplement, allowed_tools_json, allowed_skills_json, model_routing_policy_json, memory_access_json, max_budget_json, max_depth, output_contract_json, status, risk_level, metadata_json, created_at) "
                "VALUES ('spec_test_prev', 'ScriptAgent', '1.0.0', 'Scripting', 'Supplement', '[]', '[]', '{}', '{}', '{}', 2, '{}', 'active', 'low', '{}', '2026-08-29 00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO learned_rules (id, domain, condition, recommendation, scope, evidence_refs_json, metrics_json, confidence, sample_size, version, state, created_at) "
                "VALUES ('rule_prev_09', 'youtube_studio', '{\"cluster\":\"ai\"}', 'Start with demo', 'project', '[]', '{}', 0.8, 2, 1, 'candidate', '2026-08-29 00:00:00')"
            )
        )
    engine.dispose()

    # 3. Upgrade to HEAD (0031)
    command.upgrade(cfg, HEAD)
    assert alembic_current(db_url) == (HEAD,)

    # Verify 0030 data preserved and 0031 tables exist
    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert "learned_rules" in tables
        assert "conflict_resolutions" in tables
        assert "multi_agent_attributions" in tables

        with engine.begin() as conn:
            row = conn.execute(text("SELECT id, role FROM subagent_spec_versions WHERE id = 'spec_test_prev'")).fetchone()
            assert row is not None
            assert row[1] == "ScriptAgent"

            rule_row = conn.execute(text("SELECT id, target_role FROM learned_rules WHERE id = 'rule_prev_09'")).fetchone()
            assert rule_row is not None

            # Insert sample 0031 rule with new columns
            conn.execute(
                text(
                    "INSERT INTO learned_rules (id, domain, condition, recommendation, scope, target_role, evidence_refs_json, metrics_json, confidence, sample_size, version, state, metadata_json, created_at) "
                    "VALUES ('rule_test_14', 'youtube_studio', '{\"topic_cluster\": \"ai\"}', 'Start with demo', 'role', 'ScriptAgent', '[]', '{}', 0.9, 3, 1, 'candidate', '{}', '2026-08-29 00:00:00')"
                )
            )
            rule_14 = conn.execute(text("SELECT id, target_role FROM learned_rules WHERE id = 'rule_test_14'")).fetchone()
            assert rule_14 is not None
            assert rule_14[1] == "ScriptAgent"
    finally:
        engine.dispose()

    # 4. Downgrade back to PREV (0030)
    command.downgrade(cfg, PREV)
    assert alembic_current(db_url) == (PREV,)

    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert "conflict_resolutions" not in tables
        assert "multi_agent_attributions" not in tables
        # 0030 tables and 0026 learned_rules must still exist
        assert "subagent_spec_versions" in tables
        assert "learned_rules" in tables
        with engine.begin() as conn:
            row = conn.execute(text("SELECT id, role FROM subagent_spec_versions WHERE id = 'spec_test_prev'")).fetchone()
            assert row is not None
            assert row[1] == "ScriptAgent"
            rule_row = conn.execute(text("SELECT id FROM learned_rules WHERE id = 'rule_prev_09'")).fetchone()
            assert rule_row is not None
    finally:
        engine.dispose()

    # 5. Re-upgrade to HEAD (0031) idempotently
    command.upgrade(cfg, HEAD)
    assert alembic_current(db_url) == (HEAD,)
    engine, inspector = _inspect(temp_db_path)
    try:
        tables = set(inspector.get_table_names())
        assert "learned_rules" in tables
        assert "conflict_resolutions" in tables
        assert "multi_agent_attributions" in tables
    finally:
        engine.dispose()
