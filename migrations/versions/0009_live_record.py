"""Live Record bounded context tables (Phase 17).

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "live_execution_plans",
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("episode_id", sa.String(length=64), nullable=False),
        sa.Column("episode_revision_id", sa.String(length=64), nullable=False),
        sa.Column("preparation_revision", sa.Integer(), nullable=False),
        sa.Column("plan_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("director_role", sa.String(length=32), nullable=False),
        sa.Column("recording_profile_json", sa.Text(), nullable=False),
        sa.Column("scenes_json", sa.Text(), nullable=False),
        sa.Column("actions_json", sa.Text(), nullable=False),
        sa.Column("payload_bundles_json", sa.Text(), nullable=False),
        sa.Column("source_workspace_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("plan_id", name=op.f("pk_live_execution_plans")),
    )
    op.create_index(op.f("ix_live_execution_plans_episode_id"), "live_execution_plans", ["episode_id"], unique=False)
    op.create_index("ix_live_plans_episode_status", "live_execution_plans", ["episode_id", "status"], unique=False)
    op.create_table(
        "live_record_takes",
        sa.Column("take_id", sa.String(length=64), nullable=False),
        sa.Column("execution_plan_id", sa.String(length=64), nullable=False),
        sa.Column("execution_plan_hash", sa.String(length=64), nullable=False),
        sa.Column("episode_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("take_id", name=op.f("pk_live_record_takes")),
    )
    op.create_index(op.f("ix_live_record_takes_episode_id"), "live_record_takes", ["episode_id"], unique=False)
    op.create_index(op.f("ix_live_record_takes_execution_plan_id"), "live_record_takes", ["execution_plan_id"], unique=False)
    op.create_table(
        "live_record_segments",
        sa.Column("segment_id", sa.String(length=64), nullable=False),
        sa.Column("take_id", sa.String(length=64), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("file_token", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("is_playable", sa.Boolean(), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("segment_id", name=op.f("pk_live_record_segments")),
        sa.UniqueConstraint("take_id", "segment_index", name="uq_live_segment_take_index"),
    )
    op.create_index(op.f("ix_live_record_segments_take_id"), "live_record_segments", ["take_id"], unique=False)
    op.create_table(
        "live_record_events",
        sa.Column("take_id", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("t", sa.Float(), nullable=False),
        sa.Column("scene_id", sa.String(length=64), nullable=True),
        sa.Column("cue_id", sa.String(length=64), nullable=True),
        sa.Column("action_id", sa.String(length=64), nullable=True),
        sa.Column("segment_id", sa.String(length=64), nullable=True),
        sa.Column("execution_id", sa.String(length=64), nullable=True),
        sa.Column("marker_type", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("take_id", "seq", name=op.f("pk_live_record_events")),
    )
    op.create_index("ix_live_events_take_t", "live_record_events", ["take_id", "t"], unique=False)
    op.create_table(
        "director_sessions",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("execution_plan_id", sa.String(length=64), nullable=False),
        sa.Column("execution_plan_hash", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=True),
        sa.Column("model_id", sa.String(length=128), nullable=True),
        sa.Column("connection_state", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_director_sessions")),
    )
    op.create_index(op.f("ix_director_sessions_execution_plan_id"), "director_sessions", ["execution_plan_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_director_sessions_execution_plan_id"), table_name="director_sessions")
    op.drop_table("director_sessions")
    op.drop_index("ix_live_events_take_t", table_name="live_record_events")
    op.drop_table("live_record_events")
    op.drop_index(op.f("ix_live_record_segments_take_id"), table_name="live_record_segments")
    op.drop_table("live_record_segments")
    op.drop_index(op.f("ix_live_record_takes_execution_plan_id"), table_name="live_record_takes")
    op.drop_index(op.f("ix_live_record_takes_episode_id"), table_name="live_record_takes")
    op.drop_table("live_record_takes")
    op.drop_index("ix_live_plans_episode_status", table_name="live_execution_plans")
    op.drop_index(op.f("ix_live_execution_plans_episode_id"), table_name="live_execution_plans")
    op.drop_table("live_execution_plans")
