"""0006 durable plan scheduler

Revision ID: 0006_durable_plan_scheduler
Revises: 0005_orchestrator_agent_turns
Create Date: 2026-08-03

Phase 4 adds the durable lock used while a plan node is running.  Scheduler
claims are persisted rather than inferred from an in-memory worker registry,
so concurrency groups survive restarts and release only at a terminal state.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_durable_plan_scheduler"
down_revision = "0005_orchestrator_agent_turns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("fencing_token", sa.String(192), nullable=True))
    op.create_table(
        "task_concurrency_locks",
        sa.Column("lock_key", sa.String(256), primary_key=True),
        sa.Column(
            "parent_task_id",
            sa.String(36),
            sa.ForeignKey("parent_tasks.parent_task_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("concurrency_group", sa.String(128), nullable=False),
        sa.Column(
            "task_node_run_id",
            sa.String(64),
            sa.ForeignKey("task_node_runs.task_node_run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_node_run_id", name="uq_concurrency_lock_node_run"),
    )
    op.create_index(
        "ix_task_concurrency_locks_parent_group",
        "task_concurrency_locks",
        ["parent_task_id", "concurrency_group"],
    )


def downgrade() -> None:
    op.drop_table("task_concurrency_locks")
    op.drop_column("agent_runs", "fencing_token")
