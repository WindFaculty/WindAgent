"""Memory bounded context tables (Phase 14).

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_records",
        sa.Column("memory_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=256), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("provenance_source", sa.String(length=256), nullable=False),
        sa.Column("tags_json", sa.Text(), nullable=False),
        sa.Column("ttl_seconds", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("learning_metadata_json", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("memory_id", name=op.f("pk_memory_records")),
    )
    op.create_index(op.f("ix_memory_records_scope"), "memory_records", ["scope"], unique=False)
    op.create_index(op.f("ix_memory_records_key"), "memory_records", ["key"], unique=False)
    op.create_index(op.f("ix_memory_records_project_id"), "memory_records", ["project_id"], unique=False)
    op.create_index(op.f("ix_memory_records_session_id"), "memory_records", ["session_id"], unique=False)
    op.create_index(op.f("ix_memory_records_content_hash"), "memory_records", ["content_hash"], unique=False)
    op.create_index(
        op.f("ix_memory_records_lookup"),
        "memory_records",
        ["scope", "key", "project_id", "session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_memory_records_lookup"), table_name="memory_records")
    op.drop_index(op.f("ix_memory_records_content_hash"), table_name="memory_records")
    op.drop_index(op.f("ix_memory_records_session_id"), table_name="memory_records")
    op.drop_index(op.f("ix_memory_records_project_id"), table_name="memory_records")
    op.drop_index(op.f("ix_memory_records_key"), table_name="memory_records")
    op.drop_index(op.f("ix_memory_records_scope"), table_name="memory_records")
    op.drop_table("memory_records")
