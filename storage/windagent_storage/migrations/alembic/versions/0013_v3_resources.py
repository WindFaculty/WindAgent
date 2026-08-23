"""0013 namespaced durable V3 resource authority (Phase 4).

Revision ID: 0013_v3_resources
Revises: 0012_studio_artifact_provenance
Create Date: 2026-08-20

Phase 4 migrates every canonical mutable V3 router aggregate (projects,
episodes, tasks, workflows, providers, models, routing, assets, reviews,
world, storyboard, characters, production, agent definitions/instances,
conversations) from module-level RAM stores to a durable SQL authority.

This migration creates the single namespaced ``v3_resources`` table that backs
those aggregates:

- ``namespace`` + ``resource_id`` is the canonical aggregate key and is unique.
- ``(namespace, idempotency_key)`` is unique for non-null idempotency keys so
  durable idempotent creation is enforced at the database boundary.
- ``version`` provides optimistic concurrency (compare-and-swap).
- ``data_json`` holds the full resource payload.

The migration is reversible: downgrade drops the table and its indexes only.
``if_not_exists`` makes the upgrade safe on databases where a previous
metadata ``create_all`` already materialized the table.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0013_v3_resources"
down_revision = "0012_studio_artifact_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v3_resources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("namespace", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_index(
        "ix_v3_resources_namespace_id",
        "v3_resources",
        ["namespace", "resource_id"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "ix_v3_resources_namespace_idem",
        "v3_resources",
        ["namespace", "idempotency_key"],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_v3_resources_namespace_idem",
        table_name="v3_resources",
        if_exists=True,
    )
    op.drop_index(
        "ix_v3_resources_namespace_id",
        table_name="v3_resources",
        if_exists=True,
    )
    op.drop_table("v3_resources")
