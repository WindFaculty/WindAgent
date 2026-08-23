"""0018 fix timestamptz for PostgreSQL (P1.8 production readiness).

Revision ID: 0018_fix_timestamptz
Revises: 0017_route_receipts
Create Date: 2026-08-23

PG failure: v3_resources and other tables used TIMESTAMP WITHOUT TIME ZONE
while Python passes aware UTC datetimes (default_utc_now). On SQLite
TEXT storage the mismatch is silent; on PostgreSQL asyncpg rejects
aware datetime for WITHOUT TZ columns.

Root: v3_models and v2_orchestration_models defined DateTime without
timezone=True, and migrations 0013/0017 created TIMESTAMP WITHOUT TZ.

Fix: ORM now declares DateTime(timezone=True) for all timestamp columns.
Fresh databases created via 0001 baseline now get TIMESTAMPTZ directly.
Existing PostgreSQL databases that already have WITHOUT TZ columns are
altered here to TIMESTAMPTZ USING column AT TIME ZONE 'UTC'.

SQLite: no-op (SQLite has no type enforcement).

Downgrade is no-op for PG (reverting would lose timezone info).
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text

revision = "0018_fix_timestamptz"
down_revision = "0017_route_receipts"
branch_labels = None
depends_on = None


def _alter_to_timestamptz(table: str, column: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # Check current data_type; only alter if WITHOUT TIME ZONE.
    res = bind.execute(text("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = :table AND column_name = :column
    """), {"table": table, "column": column}).fetchone()
    if res is None:
        return
    data_type = str(res[0]).lower()
    # data_type for WITH TZ is 'timestamp with time zone', without is 'timestamp without time zone'
    if "without time zone" in data_type or data_type == "timestamp without time zone":
        # Use USING clause to interpret existing naive timestamps as UTC.
        bind.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE TIMESTAMPTZ USING "{column}" AT TIME ZONE \'UTC\''))


def upgrade() -> None:
    # Concrete list derived from v3_models + v2_orchestration_models DateTime columns.
    targets = [
        ("v3_resources", "created_at"),
        ("v3_resources", "updated_at"),
        ("provider_vendors", "created_at"),
        ("provider_vendors", "updated_at"),
        ("provider_credentials", "created_at"),
        ("provider_credentials", "updated_at"),
        ("provider_endpoints", "last_tested_at"),
        ("provider_endpoints", "created_at"),
        ("provider_endpoints", "updated_at"),
        ("canonical_models_v3", "created_at"),
        ("canonical_models_v3", "updated_at"),
        ("endpoint_model_bindings", "last_discovered_at"),
        ("endpoint_model_bindings", "created_at"),
        ("endpoint_model_bindings", "updated_at"),
        ("model_routing_rules_v3", "created_at"),
        ("model_routing_rules_v3", "updated_at"),
        ("route_locks_v3", "created_at"),
        ("route_locks_v3", "updated_at"),
        ("route_locks_v3", "released_at"),
        ("provider_routing_audit_v3", "created_at"),
        ("route_attempts_v3", "started_at"),
        ("route_attempts_v3", "first_token_at"),
        ("route_attempts_v3", "finished_at"),
        ("endpoint_runtime_state", "cooldown_until"),
        ("endpoint_runtime_state", "last_429_at"),
        ("endpoint_runtime_state", "last_failure_at"),
        ("endpoint_runtime_state", "updated_at"),
        ("endpoint_health_samples", "sampled_at"),
        ("endpoint_rate_limit_windows", "window_start_at"),
        ("provider_quota_snapshots_v3", "reset_at"),
        ("provider_quota_snapshots_v3", "created_at"),
        ("provider_usage_ledger", "created_at"),
        ("model_discovery_snapshots", "discovered_at"),
        ("response_cache_entries", "expires_at"),
        ("response_cache_entries", "created_at"),
        ("model_route_receipts_v3", "started_at"),
        ("model_route_receipts_v3", "completed_at"),
        ("model_route_receipts_v3", "created_at"),
        # v2 orchestration tables (created via 0001 baseline, may be WITHOUT TZ on old PG DBs)
        ("agent_sessions", "created_at"),
        ("agent_sessions", "updated_at"),
        ("parent_tasks", "created_at"),
        ("parent_tasks", "updated_at"),
        ("task_plan_versions", "created_at"),
        ("task_nodes", "created_at"),
        ("task_node_runs", "created_at"),
        ("task_node_runs", "updated_at"),
        ("tool_executions", "created_at"),
        ("tool_executions", "updated_at"),
        ("worktrees", "created_at"),
        ("worktrees", "updated_at"),
        ("conversations", "created_at"),
        ("conversations", "updated_at"),
        ("conversation_events", "created_at"),
        ("agent_runs", "created_at"),
        ("agent_runs", "updated_at"),
        ("agent_turns", "created_at"),
        ("agent_turns", "finished_at"),
        ("task_concurrency_locks", "created_at"),
        ("task_concurrency_locks", "updated_at"),
        ("partial_stream_artifacts", "created_at"),
        ("execution_leases", "created_at"),
        ("execution_leases", "updated_at"),
        ("execution_leases", "released_at"),
    ]
    for table, column in targets:
        # Only attempt if table exists (fresh DB may not have all legacy tables)
        bind = op.get_bind()
        inspector = inspect(bind)
        if table not in set(inspector.get_table_names()):
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        if column not in cols:
            continue
        _alter_to_timestamptz(table, column)


def downgrade() -> None:
    # No downgrade: reverting TIMESTAMPTZ to WITHOUT TZ would lose timezone.
    pass
