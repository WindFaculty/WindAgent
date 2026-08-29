"""0020 agent loop durable state & budget (Phase 2)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0020_agent_loop_budget"
down_revision = "0019_live_record_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "agent_loop_states" not in existing:
        op.create_table(
            "agent_loop_states",
            sa.Column("agent_run_id", sa.String(64), primary_key=True),
            sa.Column("state", sa.String(32), nullable=False, server_default="CREATED"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("budget_limits_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("budget_usage_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("budget_scope", sa.String(32), nullable=False, server_default="conversation"),
            sa.Column("exhaustion_reason", sa.String(64), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_agent_loop_states_state", "agent_loop_states", ["state"])
        op.create_index("ix_agent_loop_states_scope", "agent_loop_states", ["budget_scope"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "agent_loop_states" in existing:
        op.drop_table("agent_loop_states")
