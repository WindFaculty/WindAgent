"""0003 multi-agent canonical aggregates

Revision ID: 0003_multi_agent_canonical
Revises: 0002_legacy_v2_data
Create Date: 2026-08-03

Phase 1 — G1.2 / G1.3. Creates the canonical multi-agent aggregate tables
(ADR 0006 / ``docs/architecture/multi_agent_schema_mapping.md``) with the
integrity constraints required by the plan:

- ``conversations``: aggregate root for the workspace.
- ``parent_tasks``:  FK + index on ``conversation_id``.
- ``agent_instances``: FK + index on ``conversation_id``.
- ``agent_sessions``: **unique** ``windagent_session_id``; ``version`` CAS column.
- ``task_plan_versions``: immutable plan snapshots — every edit inserts a new
  row with a bumped ``version``; running runs pin the old ``plan_version_id``.
- ``task_nodes`` / ``task_edges``: DAG definition per plan version.
- ``task_node_runs``: persisted node/dependency/retry state + ``version`` CAS,
  ``concurrency_group``, ``next_retry_at``, ``routing_snapshot_json``.
- ``tool_executions``: **unique** ``idempotency_key`` (retry de-dup).
- ``worktrees``: per coding-agent worktree lifecycle.
- ``conversation_events``: conversation-scoped event envelope store (G6.1).

Route-lock uniqueness (unique active per scope) already exists on
``route_locks_v3`` and is not re-created here.

Data lanes (additive, no data loss): ``chat_sessions`` -> ``conversations``,
``v2_tasks`` -> ``parent_tasks``, ``v2_workflow_runs_v2`` -> ``task_plan_versions``.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_multi_agent_canonical"
down_revision = "0002_legacy_v2_data"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    """Live DDL check — never uses the (possibly stale) cached Inspector."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return bool(
            bind.execute(
                sa.text("SELECT to_regclass(:name) IS NOT NULL"), {"name": name}
            ).scalar()
        )
    row = bind.execute(
        sa.text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
        ),
        {"name": name},
    ).fetchone()
    return row is not None


def _count(name: str) -> int:
    bind = op.get_bind()
    return bind.execute(sa.text(f"SELECT COUNT(*) FROM {name}")).scalar() or 0


def _insert_select(select_sql: str, expected: int) -> None:
    """Execute an ``INSERT INTO t (...) SELECT ...`` idempotently per dialect.

    SQLite does not accept a trailing ``ON CONFLICT`` clause on the
    INSERT...SELECT...FROM form, so it uses ``INSERT OR IGNORE``; PostgreSQL
    gets ``ON CONFLICT DO NOTHING``.

    The affected-row count must equal ``expected`` (the source row count): a
    shorter count means rows were silently skipped by the conflict clause and
    the migration fails loudly instead of losing data (Phase 1 exit gate).
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        result = bind.execute(sa.text(select_sql + " ON CONFLICT DO NOTHING"))
    else:
        result = bind.execute(sa.text(select_sql.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)))
    inserted = result.rowcount if result is not None else 0
    if inserted != expected:
        raise RuntimeError(
            f"Migration 0003 data lane expected {expected} rows but inserted "
            f"{inserted} — rows were skipped by the upsert; refusing to proceed "
            "to avoid silent data loss."
        )


def upgrade() -> None:
    # Stage the legacy parent_tasks table so the new canonical table can reuse
    # the name without colliding (Phase 1 data lane: legacy parent_tasks was
    # already consumed by 0002 into v2_tasks).
    if _table_exists("parent_tasks"):
        op.execute("ALTER TABLE parent_tasks RENAME TO legacy_parent_tasks_snapshot")

    # ------------------------------------------------------------------ #
    # conversations
    # ------------------------------------------------------------------ #
    op.create_table(
        "conversations",
        sa.Column("conversation_id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="idle"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("last_event_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------------------------ #
    # parent_tasks  (FK + index on conversation_id — G1.2)
    # ------------------------------------------------------------------ #
    op.create_table(
        "parent_tasks",
        sa.Column("parent_task_id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("active_plan_version_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_parent_tasks_conversation_id", "parent_tasks", ["conversation_id"]
    )

    # ------------------------------------------------------------------ #
    # task_plan_versions  (immutable plan snapshots — G1.3)
    # ------------------------------------------------------------------ #
    op.create_table(
        "task_plan_versions",
        sa.Column("plan_version_id", sa.String(64), primary_key=True),
        sa.Column(
            "parent_task_id",
            sa.String(36),
            sa.ForeignKey("parent_tasks.parent_task_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("dag_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_task_plan_versions_parent_task", "task_plan_versions", ["parent_task_id"]
    )

    # ------------------------------------------------------------------ #
    # task_nodes / task_edges (DAG per plan version)
    # ------------------------------------------------------------------ #
    op.create_table(
        "task_nodes",
        sa.Column("node_id", sa.String(64), primary_key=True),
        sa.Column(
            "plan_version_id",
            sa.String(64),
            sa.ForeignKey("task_plan_versions.plan_version_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("agent_type", sa.String(64), nullable=True),
        sa.Column("tool_name", sa.String(64), nullable=True),
        sa.Column("params_json", sa.Text(), nullable=True),
        sa.Column("concurrency_group", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_task_nodes_plan_version", "task_nodes", ["plan_version_id"]
    )
    op.create_table(
        "task_edges",
        sa.Column("edge_id", sa.String(64), primary_key=True),
        sa.Column(
            "plan_version_id",
            sa.String(64),
            sa.ForeignKey("task_plan_versions.plan_version_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_node_id", sa.String(64), nullable=False),
        sa.Column("to_node_id", sa.String(64), nullable=False),
    )
    op.create_index(
        "ix_task_edges_plan_version", "task_edges", ["plan_version_id"]
    )

    # ------------------------------------------------------------------ #
    # agent_instances  (FK + index on conversation_id — G1.2)
    # ------------------------------------------------------------------ #
    op.create_table(
        "agent_instances",
        sa.Column("agent_instance_id", sa.String(64), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_task_id",
            sa.String(36),
            sa.ForeignKey("parent_tasks.parent_task_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent_type", sa.String(64), nullable=False),
        sa.Column("permission_profile_json", sa.Text(), nullable=True),
        sa.Column("canonical_model_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("assigned_node_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_agent_instances_conversation_id", "agent_instances", ["conversation_id"]
    )

    # ------------------------------------------------------------------ #
    # agent_sessions  (unique windagent_session_id — G1.2; version CAS)
    # ------------------------------------------------------------------ #
    op.create_table(
        "agent_sessions",
        sa.Column("agent_session_id", sa.String(64), primary_key=True),
        sa.Column(
            "agent_instance_id",
            sa.String(64),
            sa.ForeignKey("agent_instances.agent_instance_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("windagent_session_id", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "windagent_session_id", name="uq_agent_sessions_windagent_session_id"
        ),
        sa.Column("runtime_locator", sa.String(255), nullable=True),
        sa.Column("hermes_run_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="idle"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_agent_sessions_agent_instance", "agent_sessions", ["agent_instance_id"]
    )

    # ------------------------------------------------------------------ #
    # task_node_runs  (persisted state + CAS version — G1.2)
    # ------------------------------------------------------------------ #
    op.create_table(
        "task_node_runs",
        sa.Column("task_node_run_id", sa.String(64), primary_key=True),
        sa.Column(
            "plan_version_id",
            sa.String(64),
            sa.ForeignKey("task_plan_versions.plan_version_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("node_id", sa.String(64), nullable=False),
        sa.Column(
            "parent_task_id",
            sa.String(36),
            sa.ForeignKey("parent_tasks.parent_task_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("state", sa.String(32), nullable=False, server_default="received"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("facts_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("dependency_state_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("retry_state_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("routing_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("concurrency_group", sa.String(128), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_task_node_runs_plan_version", "task_node_runs", ["plan_version_id"]
    )

    # ------------------------------------------------------------------ #
    # tool_executions  (unique idempotency_key — G1.2 / G4.3)
    # ------------------------------------------------------------------ #
    op.create_table(
        "tool_executions",
        sa.Column("tool_execution_id", sa.String(64), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_tool_executions_idempotency_key"
        ),
        sa.Column(
            "agent_instance_id",
            sa.String(64),
            sa.ForeignKey("agent_instances.agent_instance_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("arguments_redacted", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="reserved"),
        sa.Column("result_ref", sa.String(256), nullable=True),
        sa.Column("claimant", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_tool_executions_agent_instance", "tool_executions", ["agent_instance_id"]
    )

    # ------------------------------------------------------------------ #
    # worktrees  (per coding agent — G5.x foundation)
    # ------------------------------------------------------------------ #
    op.create_table(
        "worktrees",
        sa.Column("worktree_id", sa.String(64), primary_key=True),
        sa.Column(
            "agent_instance_id",
            sa.String(64),
            sa.ForeignKey("agent_instances.agent_instance_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("branch", sa.String(255), nullable=False),
        sa.Column("repo_root", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_worktrees_agent_instance", "worktrees", ["agent_instance_id"]
    )

    # ------------------------------------------------------------------ #
    # conversation_events  (envelope store for G6.1 multiplex)
    # ------------------------------------------------------------------ #
    op.create_table(
        "conversation_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_instance_id", sa.String(64), nullable=True),
        sa.Column("agent_session_id", sa.String(64), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_conversation_events_conversation_seq",
        "conversation_events",
        ["conversation_id", "sequence"],
    )

    # ------------------------------------------------------------------ #
    # Data lanes (additive — Phase 1 exit gate: no loss of needed data)
    # ------------------------------------------------------------------ #
    if _table_exists("chat_sessions") and _count("chat_sessions") > 0:
        _insert_select(
            """
            INSERT INTO conversations
            (conversation_id, title, status, metadata_json, last_event_sequence, created_at, updated_at)
            SELECT
                id, title, COALESCE(status, 'idle'), metadata_json,
                COALESCE(last_event_sequence, 0),
                COALESCE(created_at, CURRENT_TIMESTAMP), COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM chat_sessions
            """,
            _count("chat_sessions"),
        )

    if _table_exists("v2_tasks") and _count("v2_tasks") > 0:
        _insert_select(
            """
            INSERT INTO parent_tasks
            (parent_task_id, conversation_id, objective, status, created_at, updated_at)
            SELECT
                id, session_id, prompt, COALESCE(status, 'pending'),
                COALESCE(created_at, CURRENT_TIMESTAMP), COALESCE(created_at, CURRENT_TIMESTAMP)
            FROM v2_tasks
            """,
            _count("v2_tasks"),
        )

    if _table_exists("v2_workflow_runs_v2") and _count("v2_workflow_runs_v2") > 0:
        _insert_select(
            """
            INSERT INTO task_plan_versions
            (plan_version_id, parent_task_id, version, dag_json, created_at)
            SELECT run_id, NULL, COALESCE(version, 1), COALESCE(definition_json, '{}'),
                   COALESCE(created_at, CURRENT_TIMESTAMP)
            FROM v2_workflow_runs_v2
            """,
            _count("v2_workflow_runs_v2"),
        )


def downgrade() -> None:
    """Drop the canonical multi-agent tables in reverse dependency order."""
    for table in (
        "conversation_events",
        "worktrees",
        "tool_executions",
        "task_node_runs",
        "task_edges",
        "task_nodes",
        "agent_sessions",
        "agent_instances",
        "task_plan_versions",
        "parent_tasks",
        "conversations",
    ):
        op.drop_table(table)

    # Restore the staged legacy parent_tasks table if a downgrade follows a
    # legacy-V2 upgrade (rollback rehearsal parity).
    if _table_exists("legacy_parent_tasks_snapshot"):
        op.execute("ALTER TABLE legacy_parent_tasks_snapshot RENAME TO parent_tasks")
