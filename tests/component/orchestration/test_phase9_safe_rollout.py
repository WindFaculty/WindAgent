"""Phase 9 acceptance: release safety, shadowing, telemetry, and rehearsal."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from windagent_observability.release_metrics import ReleaseTelemetry
from windagent_orchestration.release.rollout import (
    MultiAgentReleasePolicy,
    ReleaseNotActive,
    RolloutStage,
)
from windagent_orchestration.release.shadow import ShadowOrchestrationRunner
from windagent_storage.migrations.release_rehearsal import (
    require_application_only_rollback,
    rehearse_sqlite_release,
)
from windagent_storage.migrations.runner import alembic_upgrade_head
from windagent_storage.database.connection import DatabaseManager


def test_rollout_advances_in_order_and_fail_closes_before_activation():
    production_default = MultiAgentReleasePolicy.from_environment(
        {"WINDAGENT_ENV": "production"}
    )
    assert production_default.stage is RolloutStage.SCHEMA_DUAL_READ
    policy = MultiAgentReleasePolicy(RolloutStage.SCHEMA_DUAL_READ)
    schema = policy.decision_for()
    assert schema.schema_enabled and schema.dual_read_enabled
    assert not schema.runtime_activation_enabled
    with pytest.raises(ReleaseNotActive):
        policy.require_runtime_activation()
    with pytest.raises(ValueError, match="advance one stage"):
        policy.transition_to(RolloutStage.INTERNAL_USERS)

    shadow = policy.transition_to(RolloutStage.SHADOW_ORCHESTRATION)
    assert shadow.decision_for().shadow_orchestration_enabled
    internal = shadow.transition_to(RolloutStage.INTERNAL_USERS).with_internal_actors(["staff-7"])
    assert internal.decision_for("staff-7").runtime_activation_enabled
    assert not internal.decision_for("external-3").runtime_activation_enabled
    assert internal.transition_to(RolloutStage.FULL_ACTIVATION).decision_for().runtime_activation_enabled


def test_shadow_comparison_has_no_runtime_dispatch_capability_and_records_only_parity():
    telemetry = ReleaseTelemetry()
    runner = ShadowOrchestrationRunner(telemetry)
    dispatched = False

    def shadow_planner(snapshot: dict[str, object]) -> dict[str, object]:
        nonlocal dispatched
        assert "dispatch" not in snapshot
        dispatched = False
        return {"nodes": ["research", "code"], "objective": "safe rollout"}

    comparison = runner.compare_plan(
        "goal-plan",
        {"objective": "safe rollout", "nodes": ["research", "code"]},
        shadow_planner,
    )
    assert comparison.matched
    assert not dispatched
    assert telemetry.snapshot().shadow_comparisons == 1


def test_release_telemetry_covers_all_phase9_operational_signals():
    telemetry = ReleaseTelemetry()
    telemetry.record_route_request()
    telemetry.record_route_request()
    telemetry.record_route_failover()
    telemetry.record_duplicate_tool_execution()
    telemetry.set_orphan_worktree_count(3)
    telemetry.record_websocket_reconnect()
    telemetry.record_recovery_duration(0.25)
    telemetry.record_database_lock_error()
    telemetry.record_shadow_comparison(matched=False)

    snapshot = telemetry.snapshot()
    assert snapshot.route_failover_rate == 0.5
    assert snapshot.duplicate_tool_executions == 1
    assert snapshot.orphan_worktree_count == 3
    assert snapshot.websocket_reconnects == 1
    assert snapshot.recovery_duration_max_seconds == 0.25
    assert snapshot.database_lock_errors == 1
    assert snapshot.shadow_mismatches == 1


def test_sqlite_rehearsal_preserves_immutable_plan_and_audit_data(tmp_path: Path):
    database = tmp_path / "production-copy.sqlite3"
    db_url = f"sqlite:///{database.as_posix()}"
    alembic_upgrade_head(db_url)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO conversations "
            "(conversation_id, status, last_event_sequence, created_at, updated_at) "
            "VALUES ('conversation-1', 'idle', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO parent_tasks "
            "(parent_task_id, conversation_id, objective, status, created_at, updated_at) "
            "VALUES ('task-1', 'conversation-1', 'release', 'draft', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO task_plan_versions "
            "(plan_version_id, parent_task_id, version, dag_json, created_at) "
            "VALUES ('plan-1', 'task-1', 1, '{}', CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO conversation_events "
            "(event_id, conversation_id, sequence, event_type, data_json, created_at) "
            "VALUES ('event-1', 'conversation-1', 1, 'goal_created', '{}', CURRENT_TIMESTAMP)"
        )
        connection.commit()

    receipt = rehearse_sqlite_release(database, tmp_path / "release-evidence")

    assert receipt.backup_database.exists()
    assert receipt.immutable_data_preserved
    assert receipt.dual_read_compatible
    assert receipt.downgrade_rehearsed_on_copy
    assert receipt.restore_verified
    assert receipt.application_rollback_allowed
    assert receipt.database_downgrade_prohibited
    require_application_only_rollback(receipt)

    # The source was not upgraded, downgraded, restored, or otherwise mutated.
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM task_plan_versions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM conversation_events").fetchone()[0] == 1


def test_pre_migration_backup_uses_consistent_sqlite_copy(tmp_path: Path):
    database = tmp_path / "live.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE release_probe (value TEXT NOT NULL)")
        connection.execute("INSERT INTO release_probe VALUES ('keep')")
        connection.commit()

    manager = DatabaseManager(f"sqlite+aiosqlite:///{database.as_posix()}")
    backup = manager.create_pre_migration_backup(tmp_path / "backups")
    assert backup is not None and backup.exists()
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT value FROM release_probe").fetchone()[0] == "keep"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM release_probe").fetchone()[0] == "keep"
