"""Agent Runtime bounded context tables (Phase 13).

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("budget_limits_json", sa.Text(), nullable=False),
        sa.Column("budget_usage_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_agent_sessions")),
    )
    op.create_index(op.f("ix_agent_sessions_actor_id"), "agent_sessions", ["actor_id"], unique=False)

    op.create_table(
        "agent_runs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("parent_run_id", sa.String(length=36), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("budget_scope", sa.String(length=32), nullable=False),
        sa.Column("budget_limits_json", sa.Text(), nullable=False),
        sa.Column("budget_usage_json", sa.Text(), nullable=False),
        sa.Column("exhaustion_reason", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_agent_runs")),
    )
    op.create_index(op.f("ix_agent_runs_session_id"), "agent_runs", ["session_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_parent_run_id"), "agent_runs", ["parent_run_id"], unique=False)

    op.create_table(
        "agent_tasks",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("workflow_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=True),
        sa.Column("input_payload_json", sa.Text(), nullable=False),
        sa.Column("output_payload_json", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("awaiting_approval_id", sa.String(length=36), nullable=True),
        sa.Column("checkpoint_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("task_id", name=op.f("pk_agent_tasks")),
    )
    op.create_index(op.f("ix_agent_tasks_session_id"), "agent_tasks", ["session_id"], unique=False)
    op.create_index(op.f("ix_agent_tasks_run_id"), "agent_tasks", ["run_id"], unique=False)
    op.create_index(op.f("ix_agent_tasks_workflow_id"), "agent_tasks", ["workflow_id"], unique=False)

    op.create_table(
        "agent_workflows",
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("nodes_json", sa.Text(), nullable=False),
        sa.Column("edges_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("workflow_id", name=op.f("pk_agent_workflows")),
    )
    op.create_index(op.f("ix_agent_workflows_session_id"), "agent_workflows", ["session_id"], unique=False)

    op.create_table(
        "agent_workflow_steps",
        sa.Column("step_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("node_id", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("step_id", name=op.f("pk_agent_workflow_steps")),
    )
    op.create_index(op.f("ix_agent_steps_workflow_id"), "agent_workflow_steps", ["workflow_id"], unique=False)
    op.create_index(op.f("ix_agent_steps_run_id"), "agent_workflow_steps", ["run_id"], unique=False)

    op.create_table(
        "agent_checkpoints",
        sa.Column("checkpoint_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("workflow_id", sa.String(length=36), nullable=True),
        sa.Column("step_id", sa.String(length=36), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("state_snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("checkpoint_id", name=op.f("pk_agent_checkpoints")),
    )
    op.create_index(op.f("ix_agent_checkpoints_run_id"), "agent_checkpoints", ["run_id"], unique=False)
    op.create_index(op.f("ix_agent_checkpoints_task_id"), "agent_checkpoints", ["task_id"], unique=False)

    op.create_table(
        "agent_approvals",
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("requested_by", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("resolution_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("approval_id", name=op.f("pk_agent_approvals")),
    )
    op.create_index(op.f("ix_agent_approvals_task_id"), "agent_approvals", ["task_id"], unique=False)
    op.create_index(op.f("ix_agent_approvals_run_id"), "agent_approvals", ["run_id"], unique=False)

    op.create_table(
        "agent_delegations",
        sa.Column("delegation_id", sa.String(length=36), nullable=False),
        sa.Column("parent_run_id", sa.String(length=36), nullable=False),
        sa.Column("child_run_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("delegation_id", name=op.f("pk_agent_delegations")),
    )
    op.create_index(op.f("ix_agent_delegations_parent"), "agent_delegations", ["parent_run_id"], unique=False)
    op.create_index(op.f("ix_agent_delegations_child"), "agent_delegations", ["child_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_delegations_child"), table_name="agent_delegations")
    op.drop_index(op.f("ix_agent_delegations_parent"), table_name="agent_delegations")
    op.drop_table("agent_delegations")
    op.drop_index(op.f("ix_agent_approvals_run_id"), table_name="agent_approvals")
    op.drop_index(op.f("ix_agent_approvals_task_id"), table_name="agent_approvals")
    op.drop_table("agent_approvals")
    op.drop_index(op.f("ix_agent_checkpoints_task_id"), table_name="agent_checkpoints")
    op.drop_index(op.f("ix_agent_checkpoints_run_id"), table_name="agent_checkpoints")
    op.drop_table("agent_checkpoints")
    op.drop_index(op.f("ix_agent_steps_run_id"), table_name="agent_workflow_steps")
    op.drop_index(op.f("ix_agent_steps_workflow_id"), table_name="agent_workflow_steps")
    op.drop_table("agent_workflow_steps")
    op.drop_index(op.f("ix_agent_workflows_session_id"), table_name="agent_workflows")
    op.drop_table("agent_workflows")
    op.drop_index(op.f("ix_agent_tasks_workflow_id"), table_name="agent_tasks")
    op.drop_index(op.f("ix_agent_tasks_run_id"), table_name="agent_tasks")
    op.drop_index(op.f("ix_agent_tasks_session_id"), table_name="agent_tasks")
    op.drop_table("agent_tasks")
    op.drop_index(op.f("ix_agent_runs_parent_run_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_session_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index(op.f("ix_agent_sessions_actor_id"), table_name="agent_sessions")
    op.drop_table("agent_sessions")
