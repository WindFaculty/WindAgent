"""0019 live record domain (ban_ke_hoach_v1.md Phase 1).

Revision ID: 0019_live_record_domain
Revises: 0018_fix_timestamptz
Create Date: 2026-08-23

Creates the Live Record persistence schema:

- ``live_execution_plans``  frozen execution plans (immutable after FROZEN);
  scenes/actions/payload bundles stored as JSON value objects on the row
- ``live_record_takes``     one recording run per frozen plan
- ``live_record_segments``  MKV segments of a take (tokenized file refs)
- ``live_record_events``    append-only recording timeline (TTS alignment)
- ``director_sessions``     Gemini Live director sessions bound to a plan

Additive and idempotent: fresh databases created via ``create_all`` already
carry the tables; existing databases create them only when missing.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "0019_live_record_domain"
down_revision = "0018_fix_timestamptz"
branch_labels = None
depends_on = None

_TABLES = (
    "live_execution_plans",
    "live_record_takes",
    "live_record_segments",
    "live_record_events",
    "director_sessions",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "live_execution_plans" not in existing:
        op.create_table(
            "live_execution_plans",
            sa.Column("plan_id", sa.String(64), primary_key=True),
            sa.Column("episode_id", sa.String(64), nullable=False),
            sa.Column("episode_revision_id", sa.String(64), nullable=False),
            sa.Column("preparation_revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("plan_hash", sa.String(64), nullable=False, server_default=""),
            sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
            sa.Column("director_role", sa.String(32), nullable=False, server_default="LIVE_DIRECTOR"),
            sa.Column("recording_profile_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("scenes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("actions_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("payload_bundles_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("source_workspace_hash", sa.String(64), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("optimistic_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            # Declared inline: SQLite cannot ALTER-add constraints post-create.
            sa.UniqueConstraint(
                "episode_id", "preparation_revision",
                name="uq_live_plan_episode_revision_number",
            ),
        )
        op.create_index(
            "ix_live_plans_episode_status", "live_execution_plans", ["episode_id", "status"]
        )
        op.create_index("ix_live_execution_plans_episode_id", "live_execution_plans", ["episode_id"])

    if "live_record_takes" not in existing:
        op.create_table(
            "live_record_takes",
            sa.Column("take_id", sa.String(64), primary_key=True),
            sa.Column("execution_plan_id", sa.String(64), nullable=False),
            sa.Column("execution_plan_hash", sa.String(64), nullable=False, server_default=""),
            sa.Column("episode_id", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="IDLE"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("optimistic_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index("ix_live_record_takes_execution_plan_id", "live_record_takes", ["execution_plan_id"])
        op.create_index("ix_live_record_takes_episode_id", "live_record_takes", ["episode_id"])

    if "live_record_segments" not in existing:
        op.create_table(
            "live_record_segments",
            sa.Column("segment_id", sa.String(64), primary_key=True),
            sa.Column("take_id", sa.String(64), nullable=False),
            sa.Column("segment_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("file_token", sa.String(255), nullable=False, server_default=""),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_sec", sa.Float(), nullable=True),
            sa.Column("is_playable", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("manifest_json", sa.Text(), nullable=False, server_default="{}"),
            sa.UniqueConstraint(
                "take_id", "segment_index", name="uq_live_segment_take_index"
            ),
        )
        op.create_index("ix_live_record_segments_take_id", "live_record_segments", ["take_id"])

    if "live_record_events" not in existing:
        op.create_table(
            "live_record_events",
            sa.Column("take_id", sa.String(64), primary_key=True),
            sa.Column("seq", sa.Integer(), primary_key=True),
            sa.Column("event_type", sa.String(48), nullable=False),
            sa.Column("t", sa.Float(), nullable=False, server_default="0"),
            sa.Column("scene_id", sa.String(64), nullable=True),
            sa.Column("cue_id", sa.String(64), nullable=True),
            sa.Column("action_id", sa.String(64), nullable=True),
            sa.Column("segment_id", sa.String(64), nullable=True),
            sa.Column("execution_id", sa.String(64), nullable=True),
            sa.Column("marker_type", sa.String(64), nullable=True),
            sa.Column("detail", sa.Text(), nullable=False, server_default=""),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_live_events_take_t", "live_record_events", ["take_id", "t"])

    if "director_sessions" not in existing:
        op.create_table(
            "director_sessions",
            sa.Column("session_id", sa.String(64), primary_key=True),
            sa.Column("execution_plan_id", sa.String(64), nullable=False),
            sa.Column("execution_plan_hash", sa.String(64), nullable=False, server_default=""),
            sa.Column("provider_id", sa.String(64), nullable=True),
            sa.Column("model_id", sa.String(128), nullable=True),
            sa.Column("connection_state", sa.String(32), nullable=False, server_default="DISCONNECTED"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.create_index("ix_director_sessions_execution_plan_id", "director_sessions", ["execution_plan_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    for table in reversed(_TABLES):
        if table in existing:
            op.drop_table(table)
