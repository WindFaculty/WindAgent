"""Production bounded context tables (Phase 16).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "production_projects",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_revision_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", name=op.f("pk_production_projects")),
    )
    op.create_table(
        "production_revisions",
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("parent_revision_id", sa.String(length=36), nullable=True),
        sa.Column("creator", sa.String(length=200), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("invalidation_intent", sa.String(length=40), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("revision_id", name=op.f("pk_production_revisions")),
    )
    op.create_index(op.f("ix_production_revisions_project_id"), "production_revisions", ["project_id"], unique=False)
    op.create_table(
        "production_assets",
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=400), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=30), nullable=False),
        sa.Column("processing_state", sa.String(length=30), nullable=False),
        sa.Column("active_revision_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("license_state", sa.String(length=30), nullable=False),
        sa.Column("tags_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("asset_id", name=op.f("pk_production_assets")),
    )
    op.create_index(op.f("ix_production_assets_project_id"), "production_assets", ["project_id"], unique=False)
    op.create_table(
        "production_asset_revisions",
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("supersedes_revision_id", sa.String(length=36), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=30), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("normalized_format", sa.String(length=50), nullable=True),
        sa.Column("preview_json", sa.Text(), nullable=False),
        sa.Column("validation_json", sa.Text(), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("revision_id", name=op.f("pk_production_asset_revisions")),
    )
    op.create_index(op.f("ix_production_asset_revisions_asset_id"), "production_asset_revisions", ["asset_id"], unique=False)
    op.create_table(
        "production_audio_tracks",
        sa.Column("track_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("character_id", sa.String(length=100), nullable=True),
        sa.Column("dialogue_text", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("sample_rate", sa.Integer(), nullable=False),
        sa.Column("channels", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("voice_profile_id", sa.String(length=100), nullable=True),
        sa.Column("rights_state", sa.String(length=20), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("track_id", name=op.f("pk_production_audio_tracks")),
    )
    op.create_index(op.f("ix_production_audio_tracks_project_id"), "production_audio_tracks", ["project_id"], unique=False)
    op.create_table(
        "production_mix_plans",
        sa.Column("mix_plan_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("loudness_target_lufs", sa.Float(), nullable=False),
        sa.Column("peak_ceiling_db", sa.Float(), nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=False),
        sa.Column("tracks_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("mix_plan_id", name=op.f("pk_production_mix_plans")),
    )
    op.create_index(op.f("ix_production_mix_plans_project_id"), "production_mix_plans", ["project_id"], unique=False)
    op.create_table(
        "production_code_video_projects",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("repo_url", sa.Text(), nullable=False),
        sa.Column("branch", sa.String(length=200), nullable=False),
        sa.Column("tutorial_steps_json", sa.Text(), nullable=False),
        sa.Column("current_checkpoint", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", name=op.f("pk_production_code_video_projects")),
    )
    op.create_table(
        "production_render_jobs",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("scene_id", sa.String(length=100), nullable=False),
        sa.Column("shot_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("frame_start", sa.Integer(), nullable=False),
        sa.Column("frame_end", sa.Integer(), nullable=False),
        sa.Column("colorspace", sa.String(length=50), nullable=False),
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_production_render_jobs")),
    )
    op.create_index(op.f("ix_production_render_jobs_project_id"), "production_render_jobs", ["project_id"], unique=False)
    op.create_table(
        "production_edls",
        sa.Column("edl_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("items_json", sa.Text(), nullable=False),
        sa.Column("audio_mix_plan_id", sa.String(length=36), nullable=False),
        sa.Column("subtitle_track_id", sa.String(length=100), nullable=True),
        sa.Column("encoding_profile_json", sa.Text(), nullable=False),
        sa.Column("edl_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("edl_id", name=op.f("pk_production_edls")),
    )
    op.create_index(op.f("ix_production_edls_project_id"), "production_edls", ["project_id"], unique=False)
    op.create_index(op.f("ix_production_edls_revision_id"), "production_edls", ["revision_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_production_edls_revision_id"), table_name="production_edls")
    op.drop_index(op.f("ix_production_edls_project_id"), table_name="production_edls")
    op.drop_table("production_edls")
    op.drop_index(op.f("ix_production_render_jobs_project_id"), table_name="production_render_jobs")
    op.drop_table("production_render_jobs")
    op.drop_table("production_code_video_projects")
    op.drop_index(op.f("ix_production_mix_plans_project_id"), table_name="production_mix_plans")
    op.drop_table("production_mix_plans")
    op.drop_index(op.f("ix_production_audio_tracks_project_id"), table_name="production_audio_tracks")
    op.drop_table("production_audio_tracks")
    op.drop_index(op.f("ix_production_asset_revisions_asset_id"), table_name="production_asset_revisions")
    op.drop_table("production_asset_revisions")
    op.drop_index(op.f("ix_production_assets_project_id"), table_name="production_assets")
    op.drop_table("production_assets")
    op.drop_index(op.f("ix_production_revisions_project_id"), table_name="production_revisions")
    op.drop_table("production_revisions")
    op.drop_table("production_projects")
