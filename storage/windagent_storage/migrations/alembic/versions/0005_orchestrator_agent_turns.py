"""0005 durable orchestrator provider turns

Revision ID: 0005_orchestrator_agent_turns
Revises: 0004_orchestrator_agent_runs
Create Date: 2026-08-03

Phase 3 makes provider execution a first-class, auditable conversation action.
Each AgentTurn records the immutable route-lock snapshot that governed the
request; RouteAttempt rows then describe the exact same-model failover path.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_orchestrator_agent_turns"
down_revision = "0004_orchestrator_agent_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_turns",
        sa.Column("turn_id", sa.String(64), primary_key=True),
        sa.Column(
            "agent_run_id",
            sa.String(64),
            sa.ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_session_id",
            sa.String(64),
            sa.ForeignKey("agent_sessions.agent_session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "route_lock_id",
            sa.String(128),
            sa.ForeignKey("route_locks_v3.id"),
            nullable=False,
        ),
        sa.Column("canonical_model_id", sa.String(128), nullable=False),
        sa.Column("routing_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("response_summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("error_class", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_turns_run_created", "agent_turns", ["agent_run_id", "created_at"])
    op.create_index("ix_agent_turns_lock_created", "agent_turns", ["route_lock_id", "created_at"])


def downgrade() -> None:
    op.drop_table("agent_turns")
