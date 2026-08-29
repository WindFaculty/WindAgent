"""0004 orchestrator runtime ownership

Revision ID: 0004_orchestrator_agent_runs
Revises: 0003_multi_agent_canonical
Create Date: 2026-08-03

Phase 2 adds the durable runtime record which binds an AgentInstance and its
AgentSession to one concrete runtime invocation.  ``task_node_runs`` keeps the
DAG state; ``agent_runs`` keeps the independently cancellable runtime handle.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_orchestrator_agent_runs"
down_revision = "0003_multi_agent_canonical"
branch_labels = None
depends_on = None


def _canonical_model_exists(model_id: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM canonical_models_v3 WHERE id=:id"),
            {"id": model_id},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()
    if "agent_runs" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "agent_runs",
            sa.Column("agent_run_id", sa.String(64), primary_key=True),
            sa.Column(
                "agent_instance_id",
                sa.String(64),
                sa.ForeignKey("agent_instances.agent_instance_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "agent_session_id",
                sa.String(64),
                sa.ForeignKey("agent_sessions.agent_session_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "parent_task_id",
                sa.String(36),
                sa.ForeignKey("parent_tasks.parent_task_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "plan_version_id",
                sa.String(64),
                sa.ForeignKey("task_plan_versions.plan_version_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "task_node_run_id",
                sa.String(64),
                sa.ForeignKey("task_node_runs.task_node_run_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("runtime_handle_id", sa.String(128), nullable=True),
            sa.Column("runtime_run_id", sa.String(128), nullable=True, index=True),
            sa.Column("runtime_locator", sa.String(255), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="dispatching"),
            sa.Column("routing_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_agent_runs_instance_status", "agent_runs", ["agent_instance_id", "status"])
        op.create_index("ix_agent_runs_session_status", "agent_runs", ["agent_session_id", "status"])

    # The Phase-2 local-agent control-plane route is a canonical model too.  It
    # is intentionally a model record (rather than a hidden fallback) so every
    # dispatch can be pinned and audited through RouteLockService.  A real
    # provider binding can replace it later without changing existing locks.
    if not _canonical_model_exists("windagent/local-agent"):
        op.execute(
            sa.text(
                """
                INSERT INTO canonical_models_v3
                (id, vendor, family, canonical_name, revision, context_window,
                 capabilities_json, enabled, created_at, updated_at)
                VALUES
                ('windagent/local-agent', 'windagent', 'local-agent', 'WindAgent Local Agent',
                 'v1', 128000, '["tool_use"]', TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )


def downgrade() -> None:
    op.drop_table("agent_runs")
