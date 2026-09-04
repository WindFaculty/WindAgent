"""Durable tables for the Production bounded context."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Table, Text

from windagent.platform.persistence.metadata import metadata

production_projects_table = Table(
    "production_projects",
    metadata,
    Column("project_id", String(36), primary_key=True),
    Column("title", String(400), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("owner_id", String(100), nullable=False, default="system"),
    Column("status", String(30), nullable=False, default="DRAFT"),
    Column("current_revision_id", String(36), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=False, default="{}"),
)

production_revisions_table = Table(
    "production_revisions",
    metadata,
    Column("revision_id", String(36), primary_key=True),
    Column("project_id", String(36), nullable=False),
    Column("parent_revision_id", String(36), nullable=True),
    Column("creator", String(200), nullable=False),
    Column("actor", String(200), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("content_hash", String(64), nullable=False),
    Column("status", String(20), nullable=False, default="DRAFT"),
    Column("locked", Boolean, nullable=False, default=False),
    Column("invalidation_intent", String(40), nullable=True),
    Column("summary", Text, nullable=False, default=""),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=False, default="{}"),
)

production_assets_table = Table(
    "production_assets",
    metadata,
    Column("asset_id", String(36), primary_key=True),
    Column("project_id", String(36), nullable=True),
    Column("name", String(400), nullable=False),
    Column("kind", String(50), nullable=False, default="OTHER"),
    Column("lifecycle_state", String(30), nullable=False, default="DISCOVERED"),
    Column("processing_state", String(30), nullable=False, default="IDLE"),
    Column("active_revision_id", String(36), nullable=True),
    Column("source_type", String(30), nullable=False, default="UPLOADED"),
    Column("license_state", String(30), nullable=False, default="UNKNOWN"),
    Column("tags_json", Text, nullable=False, default="[]"),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=False, default="{}"),
)

production_asset_revisions_table = Table(
    "production_asset_revisions",
    metadata,
    Column("revision_id", String(36), primary_key=True),
    Column("asset_id", String(36), nullable=False),
    Column("supersedes_revision_id", String(36), nullable=True),
    Column("content_hash", String(64), nullable=False),
    Column("media_type", String(30), nullable=False, default="IMAGE"),
    Column("mime_type", String(100), nullable=False, default="image/png"),
    Column("size_bytes", Integer, nullable=False, default=0),
    Column("normalized_format", String(50), nullable=True),
    Column("preview_json", Text, nullable=False, default="{}"),
    Column("validation_json", Text, nullable=False, default="{}"),
    Column("provenance_json", Text, nullable=False, default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=True),
)

production_audio_tracks_table = Table(
    "production_audio_tracks",
    metadata,
    Column("track_id", String(36), primary_key=True),
    Column("project_id", String(36), nullable=False),
    Column("kind", String(20), nullable=False, default="DIALOGUE"),
    Column("title", String(400), nullable=False),
    Column("character_id", String(100), nullable=True),
    Column("dialogue_text", Text, nullable=False, default=""),
    Column("source_path", Text, nullable=False, default=""),
    Column("source_hash", String(64), nullable=False, default=""),
    Column("sample_rate", Integer, nullable=False, default=48000),
    Column("channels", Integer, nullable=False, default=1),
    Column("duration_seconds", Float, nullable=False, default=0.0),
    Column("language", String(20), nullable=False, default="en"),
    Column("voice_profile_id", String(100), nullable=True),
    Column("rights_state", String(20), nullable=False, default="PENDING"),
    Column("provenance_json", Text, nullable=False, default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("metadata_json", Text, nullable=False, default="{}"),
)

production_mix_plans_table = Table(
    "production_mix_plans",
    metadata,
    Column("mix_plan_id", String(36), primary_key=True),
    Column("project_id", String(36), nullable=False),
    Column("title", String(400), nullable=False, default="main"),
    Column("loudness_target_lufs", Float, nullable=False, default=-16.0),
    Column("peak_ceiling_db", Float, nullable=False, default=-1.0),
    Column("policy_version", String(50), nullable=False, default="loudness-v1"),
    Column("tracks_json", Text, nullable=False, default="[]"),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("metadata_json", Text, nullable=False, default="{}"),
)

production_code_video_projects_table = Table(
    "production_code_video_projects",
    metadata,
    Column("project_id", String(36), primary_key=True),
    Column("title", String(400), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("status", String(30), nullable=False, default="DRAFT"),
    Column("repo_url", Text, nullable=False, default=""),
    Column("branch", String(200), nullable=False, default="main"),
    Column("tutorial_steps_json", Text, nullable=False, default="[]"),
    Column("current_checkpoint", String(100), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=False, default="{}"),
)

production_render_jobs_table = Table(
    "production_render_jobs",
    metadata,
    Column("job_id", String(36), primary_key=True),
    Column("project_id", String(36), nullable=False),
    Column("revision_id", String(36), nullable=True),
    Column("scene_id", String(100), nullable=False, default=""),
    Column("shot_id", String(100), nullable=False, default=""),
    Column("status", String(20), nullable=False, default="QUEUED"),
    Column("frame_start", Integer, nullable=False, default=1),
    Column("frame_end", Integer, nullable=False, default=24),
    Column("colorspace", String(50), nullable=False, default="sRGB"),
    Column("profile_id", String(100), nullable=False, default="main_1080p_h264"),
    Column("attempt", Integer, nullable=False, default=1),
    Column("input_hash", String(64), nullable=False, default=""),
    Column("output_hash", String(64), nullable=False, default=""),
    Column("error", Text, nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=False, default="{}"),
)

production_edls_table = Table(
    "production_edls",
    metadata,
    Column("edl_id", String(36), primary_key=True),
    Column("project_id", String(36), nullable=False),
    Column("revision_id", String(36), nullable=False),
    Column("title", String(400), nullable=False, default="main"),
    Column("status", String(20), nullable=False, default="DRAFT"),
    Column("items_json", Text, nullable=False, default="[]"),
    Column("audio_mix_plan_id", String(36), nullable=False, default=""),
    Column("subtitle_track_id", String(100), nullable=True),
    Column("encoding_profile_json", Text, nullable=False, default="{}"),
    Column("edl_hash", String(64), nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("metadata_json", Text, nullable=False, default="{}"),
)
