"""SQLAlchemy table definitions for the Workspace module."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, Integer, String, Table, Text

from windagent.platform.persistence.metadata import metadata

workspaces_table = Table(
    "workspace_workspaces",
    metadata,
    Column("workspace_id", String(36), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("slug", String(100), nullable=False, unique=True),
    Column("root_path", String(500), nullable=False),
    Column("owner_id", String(100), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("status", String(50), nullable=False, default="ACTIVE"),
    Column("tier", String(50), nullable=False, default="LOCAL"),
    Column("quota_json", Text, nullable=False, default="{}"),
    Column("quota_usage_json", Text, nullable=False, default="{}"),
    Column("policy_json", Text, nullable=False, default="{}"),
    Column("metadata_json", Text, nullable=False, default="{}"),
    Column("optimistic_version", Integer, nullable=False, default=1),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_workspace_workspaces_owner", "owner_id"),
    Index("ix_workspace_workspaces_status", "status"),
)

workspace_workspaces_table = workspaces_table


workspace_members_table = Table(
    "workspace_members",
    metadata,
    Column("workspace_id", String(36), primary_key=True),
    Column("user_id", String(100), primary_key=True),
    Column("role", String(50), nullable=False, default="MEMBER"),
    Column("joined_at", DateTime(timezone=True), nullable=False),
    Index("ix_workspace_members_user", "user_id"),
)

workspace_project_bindings_table = Table(
    "workspace_project_bindings",
    metadata,
    Column("workspace_id", String(36), primary_key=True),
    Column("project_id", String(100), primary_key=True),
    Column("bound_at", DateTime(timezone=True), nullable=False),
    Index("ix_workspace_project_bindings_project", "project_id"),
)

workspace_locks_table = Table(
    "workspace_locks",
    metadata,
    Column("lock_id", String(36), primary_key=True),
    Column("workspace_id", String(36), nullable=False),
    Column("resource_type", String(100), nullable=False),
    Column("resource_id", String(200), nullable=False),
    Column("holder_id", String(100), nullable=False),
    Column("acquired_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("fencing_token", Integer, nullable=False, default=1),
    Index("ix_workspace_locks_ws_resource", "workspace_id", "resource_id", unique=True),
)

workspace_snapshots_table = Table(
    "workspace_snapshots",
    metadata,
    Column("snapshot_id", String(36), primary_key=True),
    Column("workspace_id", String(36), nullable=False),
    Column("data_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_workspace_snapshots_ws", "workspace_id", "created_at"),
)
