"""0021 durable recursive subagent delegation (Phase 4)."""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
revision = "0021_agent_delegation"
down_revision = "0020_agent_loop_budget"
branch_labels = None
depends_on = None
def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "agent_delegations" not in existing:
        op.create_table("agent_delegations", sa.Column("child_agent_run_id", sa.String(64), primary_key=True), sa.Column("parent_agent_run_id", sa.String(64), nullable=False), sa.Column("root_agent_run_id", sa.String(64), nullable=False), sa.Column("delegation_depth", sa.Integer(), nullable=False), sa.Column("delegation_reason", sa.String(255), nullable=False), sa.Column("failure_policy", sa.String(32), nullable=False, server_default="fail_parent"), sa.Column("allocated_budget_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("child_result_summary_json", sa.Text(), nullable=True), sa.Column("child_artifact_refs_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("bounded_context_json", sa.Text(), nullable=True), sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
        op.create_index("ix_agent_delegations_parent", "agent_delegations", ["parent_agent_run_id"])
        op.create_index("ix_agent_delegations_root", "agent_delegations", ["root_agent_run_id"])
        op.create_index("ix_agent_delegations_depth", "agent_delegations", ["delegation_depth"])
def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "agent_delegations" in existing:
        op.drop_table("agent_delegations")
