"""0022 long-running hardening: persistent goals + durable agent checkpoints (Phase 5)."""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0022_long_running_hardening"
down_revision = "0021_agent_delegation"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "persistent_goals" not in existing:
        op.create_table(
            "persistent_goals",
            sa.Column("goal_id", sa.String(64), primary_key=True),
            sa.Column("objective", sa.Text(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
            sa.Column("progress_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("completion_criteria_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("blocked_reason", sa.Text(), nullable=True),
            sa.Column("conversation_id", sa.String(64), nullable=True),
            sa.Column("parent_task_id", sa.String(64), nullable=True),
            sa.Column("agent_run_id", sa.String(64), nullable=True),
            sa.Column("harness_version", sa.String(32), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_persistent_goals_conversation", "persistent_goals", ["conversation_id"])
        op.create_index("ix_persistent_goals_parent", "persistent_goals", ["parent_task_id"])
        op.create_index("ix_persistent_goals_agent_run", "persistent_goals", ["agent_run_id"])
        op.create_index("ix_persistent_goals_status", "persistent_goals", ["status"])
    if "agent_checkpoints" not in existing:
        op.create_table(
            "agent_checkpoints",
            sa.Column("checkpoint_id", sa.String(64), primary_key=True),
            sa.Column("agent_run_id", sa.String(64), nullable=False),
            sa.Column("session_id", sa.String(64), nullable=True),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("step_run_id", sa.String(64), nullable=True),
            sa.Column("tool_name", sa.String(64), nullable=True),
            sa.Column("fencing_token", sa.String(128), nullable=False, server_default=""),
            sa.Column("snapshot_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("loop_version_at_checkpoint", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_agent_checkpoints_run", "agent_checkpoints", ["agent_run_id"])
        op.create_index("ix_agent_checkpoints_kind", "agent_checkpoints", ["kind"])
        op.create_index("ix_agent_checkpoints_run_seq", "agent_checkpoints", ["agent_run_id", "sequence"])
        op.create_index("ix_agent_checkpoints_run_kind", "agent_checkpoints", ["agent_run_id", "kind"])

def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "agent_checkpoints" in existing:
        op.drop_table("agent_checkpoints")
    if "persistent_goals" in existing:
        op.drop_table("persistent_goals")
