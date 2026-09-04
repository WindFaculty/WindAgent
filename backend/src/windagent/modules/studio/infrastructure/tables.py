"""Durable tables for the Studio bounded context."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, Integer, String, Table, Text

from windagent.platform.persistence.metadata import metadata

projects_table = Table(
    "studio_projects",
    metadata,
    Column("project_id", String(36), primary_key=True),
    Column("title", String(300), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("owner_id", String(100), nullable=False, default="system"),
    Column("series_ids_json", Text, nullable=False, default="[]"),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=False, default="{}"),
)

series_table = Table(
    "studio_series",
    metadata,
    Column("series_id", String(36), primary_key=True),
    Column("project_id", String(36), nullable=True),
    Column("title", String(300), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("episode_ids_json", Text, nullable=False, default="[]"),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=False, default="{}"),
    Index("ix_studio_series_project_id", "project_id"),
)

episodes_table = Table(
    "studio_episodes",
    metadata,
    Column("episode_id", String(36), primary_key=True),
    Column("series_id", String(36), nullable=False),
    Column("project_id", String(36), nullable=True),
    Column("title", String(400), nullable=False),
    Column("episode_number", Integer, nullable=False, default=1),
    Column("logline", Text, nullable=False, default=""),
    Column("state", String(50), nullable=False, default="DRAFT"),
    Column("current_revision_id", String(36), nullable=True),
    Column("active_run_id", String(36), nullable=True),
    Column("awaiting_checkpoint", String(50), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=False, default="{}"),
    Index("ix_studio_episodes_series_id", "series_id"),
)

revisions_table = Table(
    "studio_revisions",
    metadata,
    Column("revision_id", String(36), primary_key=True),
    Column("series_id", String(36), nullable=False),
    Column("episode_id", String(36), nullable=False),
    Column("parent_revision_id", String(36), nullable=True),
    Column("creator", String(200), nullable=False),
    Column("actor", String(200), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("content_hash", String(64), nullable=False),
    Column("status", String(20), nullable=False, default="DRAFT"),
    Column("lock_state", String(20), nullable=False, default="UNLOCKED"),
    Column("invalidation_intent", String(20), nullable=True),
    Column("summary", Text, nullable=False, default=""),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=False, default="{}"),
    Index("ix_studio_revisions_episode_id", "episode_id"),
)

artifacts_table = Table(
    "studio_artifacts",
    metadata,
    Column("artifact_id", String(80), primary_key=True),
    Column("artifact_type", String(100), nullable=False),
    Column("schema_version", String(50), nullable=False, default="studio.artifact/v1alpha1"),
    Column("series_id", String(36), nullable=False),
    Column("episode_id", String(36), nullable=False),
    Column("revision_id", String(36), nullable=True),
    Column("content_hash", String(64), nullable=False),
    Column("input_refs_json", Text, nullable=False, default="[]"),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("created_by", String(200), nullable=False, default="system"),
    Column("content_json", Text, nullable=False, default="{}"),
    Column("extra_json", Text, nullable=False, default="{}"),
    Index("ix_studio_artifacts_episode_id", "episode_id"),
    Index("ix_studio_artifacts_series_id", "series_id"),
)

characters_table = Table(
    "studio_characters",
    metadata,
    Column("character_id", String(36), primary_key=True),
    Column("series_id", String(36), nullable=False),
    Column("name", String(300), nullable=False),
    Column("display_name", String(300), nullable=False, default=""),
    Column("role", String(50), nullable=False, default="supporting"),
    Column("archetype", String(100), nullable=False, default=""),
    Column("description", Text, nullable=False, default=""),
    Column("traits_json", Text, nullable=False, default="[]"),
    Column("backstory", Text, nullable=False, default=""),
    Column("portrait_artifact_id", String(80), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=False, default="{}"),
    Index("ix_studio_characters_series_id", "series_id"),
)

world_locations_table = Table(
    "studio_world_locations",
    metadata,
    Column("location_id", String(100), primary_key=True),
    Column("series_id", String(36), nullable=False),
    Column("name", String(300), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("geography", Text, nullable=False, default=""),
    Column("metadata_json", Text, nullable=False, default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Index("ix_studio_world_locations_series_id", "series_id"),
)

world_props_table = Table(
    "studio_world_props",
    metadata,
    Column("prop_id", String(100), primary_key=True),
    Column("series_id", String(36), nullable=False),
    Column("name", String(300), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("significance", Text, nullable=False, default=""),
    Column("metadata_json", Text, nullable=False, default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Index("ix_studio_world_props_series_id", "series_id"),
)

storyboards_table = Table(
    "studio_storyboards",
    metadata,
    Column("storyboard_id", String(36), primary_key=True),
    Column("episode_id", String(36), nullable=False),
    Column("series_id", String(36), nullable=False),
    Column("title", String(400), nullable=False),
    Column("panels_json", Text, nullable=False, default="[]"),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=False, default="{}"),
    Index("ix_studio_storyboards_episode_id", "episode_id"),
    Index("ix_studio_storyboards_series_id", "series_id"),
)
