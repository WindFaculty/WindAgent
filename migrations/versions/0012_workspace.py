"""Workspace bounded context tables.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_workspaces",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("root_path", sa.String(length=500), nullable=False),
        sa.Column("owner_id", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="ACTIVE"),
        sa.Column("tier", sa.String(length=50), nullable=False, server_default="LOCAL"),
        sa.Column("quota_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("quota_usage_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("policy_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("optimistic_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("workspace_id", name=op.f("pk_workspace_workspaces")),
        sa.UniqueConstraint("slug", name=op.f("uq_workspace_workspaces_slug")),
    )
    op.create_index(op.f("ix_workspace_workspaces_owner"), "workspace_workspaces", ["owner_id"], unique=False)
    op.create_index(op.f("ix_workspace_workspaces_status"), "workspace_workspaces", ["status"], unique=False)

    op.create_table(
        "workspace_members",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="MEMBER"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("workspace_id", "user_id", name=op.f("pk_workspace_members")),
    )
    op.create_index(op.f("ix_workspace_members_user"), "workspace_members", ["user_id"], unique=False)

    op.create_table(
        "workspace_project_bindings",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=100), nullable=False),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("workspace_id", "project_id", name=op.f("pk_workspace_project_bindings")),
    )
    op.create_index(op.f("ix_workspace_project_bindings_project"), "workspace_project_bindings", ["project_id"], unique=False)

    op.create_table(
        "workspace_locks",
        sa.Column("lock_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=200), nullable=False),
        sa.Column("holder_id", sa.String(length=100), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fencing_token", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("lock_id", name=op.f("pk_workspace_locks")),
    )
    op.create_index(op.f("ix_workspace_locks_ws_resource"), "workspace_locks", ["workspace_id", "resource_id"], unique=True)

    op.create_table(
        "workspace_snapshots",
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("snapshot_id", name=op.f("pk_workspace_snapshots")),
    )
    op.create_index(op.f("ix_workspace_snapshots_ws"), "workspace_snapshots", ["workspace_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workspace_snapshots_ws"), table_name="workspace_snapshots")
    op.drop_table("workspace_snapshots")

    op.drop_index(op.f("ix_workspace_locks_ws_resource"), table_name="workspace_locks")
    op.drop_table("workspace_locks")

    op.drop_index(op.f("ix_workspace_project_bindings_project"), table_name="workspace_project_bindings")
    op.drop_table("workspace_project_bindings")

    op.drop_index(op.f("ix_workspace_members_user"), table_name="workspace_members")
    op.drop_table("workspace_members")

    op.drop_index(op.f("ix_workspace_workspaces_status"), table_name="workspace_workspaces")
    op.drop_index(op.f("ix_workspace_workspaces_owner"), table_name="workspace_workspaces")
    op.drop_table("workspace_workspaces")
