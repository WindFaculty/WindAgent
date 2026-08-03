"""0007 git worktree lifecycle

Revision ID: 0007_git_worktree_lifecycle
Revises: 0006_durable_plan_scheduler
Create Date: 2026-08-03

Durable state for Phase 5's Git-backed coding-agent worktrees.  A worktree is
owned by exactly one AgentInstance; cleanup retains its outcome and optional
quarantine location for recovery/audit instead of deleting the only evidence.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_git_worktree_lifecycle"
down_revision = "0006_durable_plan_scheduler"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "worktrees",
        sa.Column(
            "agent_run_id",
            sa.String(64),
            nullable=True,
        ),
    )
    op.add_column("worktrees", sa.Column("quarantine_path", sa.String(512), nullable=True))
    op.add_column("worktrees", sa.Column("cleanup_error", sa.Text(), nullable=True))
    op.add_column("worktrees", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("uq_worktrees_agent_instance", "worktrees", ["agent_instance_id"], unique=True)
    op.create_index("uq_worktrees_branch", "worktrees", ["branch"], unique=True)
    op.create_index("ix_worktrees_status", "worktrees", ["status"])


def downgrade() -> None:
    op.drop_index("ix_worktrees_status", table_name="worktrees")
    op.drop_index("uq_worktrees_branch", table_name="worktrees")
    op.drop_index("uq_worktrees_agent_instance", table_name="worktrees")
    op.drop_column("worktrees", "removed_at")
    op.drop_column("worktrees", "cleanup_error")
    op.drop_column("worktrees", "quarantine_path")
    op.drop_column("worktrees", "agent_run_id")
