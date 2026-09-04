"""Studio bounded context tables (Phase 15).

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "studio_projects",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.String(length=100), nullable=False),
        sa.Column("series_ids_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", name=op.f("pk_studio_projects")),
    )
    op.create_table(
        "studio_series",
        sa.Column("series_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("episode_ids_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("series_id", name=op.f("pk_studio_series")),
    )
    op.create_index(op.f("ix_studio_series_project_id"), "studio_series", ["project_id"], unique=False)
    op.create_table(
        "studio_episodes",
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("series_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("logline", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("current_revision_id", sa.String(length=36), nullable=True),
        sa.Column("active_run_id", sa.String(length=36), nullable=True),
        sa.Column("awaiting_checkpoint", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("episode_id", name=op.f("pk_studio_episodes")),
    )
    op.create_index(op.f("ix_studio_episodes_series_id"), "studio_episodes", ["series_id"], unique=False)
    op.create_table(
        "studio_revisions",
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("series_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("parent_revision_id", sa.String(length=36), nullable=True),
        sa.Column("creator", sa.String(length=200), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("lock_state", sa.String(length=20), nullable=False),
        sa.Column("invalidation_intent", sa.String(length=20), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("revision_id", name=op.f("pk_studio_revisions")),
    )
    op.create_index(op.f("ix_studio_revisions_episode_id"), "studio_revisions", ["episode_id"], unique=False)
    op.create_table(
        "studio_artifacts",
        sa.Column("artifact_id", sa.String(length=80), nullable=False),
        sa.Column("artifact_type", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column("series_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("input_refs_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("extra_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("artifact_id", name=op.f("pk_studio_artifacts")),
    )
    op.create_index(op.f("ix_studio_artifacts_episode_id"), "studio_artifacts", ["episode_id"], unique=False)
    op.create_index(op.f("ix_studio_artifacts_series_id"), "studio_artifacts", ["series_id"], unique=False)
    op.create_table(
        "studio_characters",
        sa.Column("character_id", sa.String(length=36), nullable=False),
        sa.Column("series_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("display_name", sa.String(length=300), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("archetype", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("traits_json", sa.Text(), nullable=False),
        sa.Column("backstory", sa.Text(), nullable=False),
        sa.Column("portrait_artifact_id", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("character_id", name=op.f("pk_studio_characters")),
    )
    op.create_index(op.f("ix_studio_characters_series_id"), "studio_characters", ["series_id"], unique=False)
    op.create_table(
        "studio_world_locations",
        sa.Column("location_id", sa.String(length=100), nullable=False),
        sa.Column("series_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("geography", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("location_id", name=op.f("pk_studio_world_locations")),
    )
    op.create_index(op.f("ix_studio_world_locations_series_id"), "studio_world_locations", ["series_id"], unique=False)
    op.create_table(
        "studio_world_props",
        sa.Column("prop_id", sa.String(length=100), nullable=False),
        sa.Column("series_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("significance", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("prop_id", name=op.f("pk_studio_world_props")),
    )
    op.create_index(op.f("ix_studio_world_props_series_id"), "studio_world_props", ["series_id"], unique=False)
    op.create_table(
        "studio_storyboards",
        sa.Column("storyboard_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("series_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("panels_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("storyboard_id", name=op.f("pk_studio_storyboards")),
    )
    op.create_index(op.f("ix_studio_storyboards_episode_id"), "studio_storyboards", ["episode_id"], unique=False)
    op.create_index(op.f("ix_studio_storyboards_series_id"), "studio_storyboards", ["series_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_studio_storyboards_series_id"), table_name="studio_storyboards")
    op.drop_index(op.f("ix_studio_storyboards_episode_id"), table_name="studio_storyboards")
    op.drop_table("studio_storyboards")
    op.drop_index(op.f("ix_studio_world_props_series_id"), table_name="studio_world_props")
    op.drop_table("studio_world_props")
    op.drop_index(op.f("ix_studio_world_locations_series_id"), table_name="studio_world_locations")
    op.drop_table("studio_world_locations")
    op.drop_index(op.f("ix_studio_characters_series_id"), table_name="studio_characters")
    op.drop_table("studio_characters")
    op.drop_index(op.f("ix_studio_artifacts_series_id"), table_name="studio_artifacts")
    op.drop_index(op.f("ix_studio_artifacts_episode_id"), table_name="studio_artifacts")
    op.drop_table("studio_artifacts")
    op.drop_index(op.f("ix_studio_revisions_episode_id"), table_name="studio_revisions")
    op.drop_table("studio_revisions")
    op.drop_index(op.f("ix_studio_episodes_series_id"), table_name="studio_episodes")
    op.drop_table("studio_episodes")
    op.drop_index(op.f("ix_studio_series_project_id"), table_name="studio_series")
    op.drop_table("studio_series")
    op.drop_table("studio_projects")
