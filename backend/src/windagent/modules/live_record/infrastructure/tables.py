"""Durable tables for the Live Record bounded context."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Table, Text

from windagent.platform.persistence.metadata import metadata

live_execution_plans_table = Table(
    "live_execution_plans",
    metadata,
    Column("plan_id", String(64), primary_key=True),
    Column("episode_id", String(64), nullable=False),
    Column("episode_revision_id", String(64), nullable=False),
    Column("preparation_revision", Integer, nullable=False, default=1),
    Column("plan_hash", String(64), nullable=False, default=""),
    Column("status", String(32), nullable=False, default="DRAFT"),
    Column("director_role", String(32), nullable=False, default="LIVE_DIRECTOR"),
    Column("recording_profile_json", Text, nullable=False, default="{}"),
    Column("scenes_json", Text, nullable=False, default="[]"),
    Column("actions_json", Text, nullable=False, default="[]"),
    Column("payload_bundles_json", Text, nullable=False, default="{}"),
    Column("source_workspace_hash", String(64), nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("frozen_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=False, default="{}"),
)

live_record_takes_table = Table(
    "live_record_takes",
    metadata,
    Column("take_id", String(64), primary_key=True),
    Column("execution_plan_id", String(64), nullable=False),
    Column("execution_plan_hash", String(64), nullable=False),
    Column("episode_id", String(64), nullable=False),
    Column("status", String(32), nullable=False, default="IDLE"),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("ended_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=False, default="{}"),
)

live_record_segments_table = Table(
    "live_record_segments",
    metadata,
    Column("segment_id", String(64), primary_key=True),
    Column("take_id", String(64), nullable=False),
    Column("segment_index", Integer, nullable=False, default=0),
    Column("file_token", String(255), nullable=False, default=""),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("ended_at", DateTime(timezone=True), nullable=True),
    Column("duration_sec", Float, nullable=True),
    Column("is_playable", Boolean, nullable=False, default=False),
    Column("manifest_json", Text, nullable=False, default="{}"),
)

live_record_events_table = Table(
    "live_record_events",
    metadata,
    Column("take_id", String(64), primary_key=True),
    Column("seq", Integer, primary_key=True),
    Column("event_type", String(48), nullable=False),
    Column("t", Float, nullable=False, default=0.0),
    Column("scene_id", String(64), nullable=True),
    Column("cue_id", String(64), nullable=True),
    Column("action_id", String(64), nullable=True),
    Column("segment_id", String(64), nullable=True),
    Column("execution_id", String(64), nullable=True),
    Column("marker_type", String(64), nullable=True),
    Column("detail", Text, nullable=False, default=""),
    Column("payload_json", Text, nullable=False, default="{}"),
    Column("occurred_at", DateTime(timezone=True), nullable=True),
)

director_sessions_table = Table(
    "director_sessions",
    metadata,
    Column("session_id", String(64), primary_key=True),
    Column("execution_plan_id", String(64), nullable=False),
    Column("execution_plan_hash", String(64), nullable=False),
    Column("provider_id", String(64), nullable=True),
    Column("model_id", String(128), nullable=True),
    Column("connection_state", String(32), nullable=False, default="DISCONNECTED"),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("metadata_json", Text, nullable=False, default="{}"),
)
