"""0008 conversation stream and recovery audit

Revision ID: 0008_conversation_stream_recovery
Revises: 0007_git_worktree_lifecycle
Create Date: 2026-08-03

Phase 6 makes ``conversation_events`` the replayable WebSocket authority and
adds an audit-only home for interrupted provider/runtime stream fragments.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_conversation_stream_recovery"
down_revision = "0007_git_worktree_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_events",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.create_index(
        "uq_conversation_events_conversation_sequence",
        "conversation_events",
        ["conversation_id", "sequence"],
        unique=True,
    )
    op.create_index(
        "uq_conversation_events_idempotency_key",
        "conversation_events",
        ["idempotency_key"],
        unique=True,
    )
    op.create_table(
        "partial_stream_artifacts",
        sa.Column("partial_artifact_id", sa.String(64), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_instance_id", sa.String(64), nullable=True),
        sa.Column("agent_session_id", sa.String(64), nullable=True),
        sa.Column("agent_run_id", sa.String(64), nullable=True),
        sa.Column("stream_id", sa.String(128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_redacted", sa.Text(), nullable=False, server_default=""),
        sa.Column("failure_reason", sa.String(512), nullable=False),
        sa.Column("audit_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_partial_stream_artifacts_conversation_sequence",
        "partial_stream_artifacts",
        ["conversation_id", "sequence"],
    )
    op.create_index(
        "ix_partial_stream_artifacts_agent_instance",
        "partial_stream_artifacts",
        ["agent_instance_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_partial_stream_artifacts_agent_instance", table_name="partial_stream_artifacts")
    op.drop_index("ix_partial_stream_artifacts_conversation_sequence", table_name="partial_stream_artifacts")
    op.drop_table("partial_stream_artifacts")
    op.drop_index("uq_conversation_events_idempotency_key", table_name="conversation_events")
    op.drop_index("uq_conversation_events_conversation_sequence", table_name="conversation_events")
    op.drop_column("conversation_events", "idempotency_key")
