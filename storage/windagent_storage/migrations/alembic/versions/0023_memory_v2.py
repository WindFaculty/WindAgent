"""0023 Memory V2 records with LearningMetadata and CAS (Phase 6) - ban_ke_hoach_v1 chapter 11."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0023_memory_v2"
down_revision = "0022_long_running_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "memory_v2_records" not in existing:
        op.create_table(
            "memory_v2_records",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("scope", sa.String(32), nullable=False),
            sa.Column("key", sa.String(128), nullable=False),
            sa.Column("value_json", sa.Text(), nullable=False),
            sa.Column("provenance_source", sa.String(128), nullable=False),
            sa.Column("project_id", sa.String(64), nullable=True),
            sa.Column("session_id", sa.String(64), nullable=True),
            sa.Column("tags_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("ttl_seconds", sa.Integer(), nullable=True),
            sa.Column("content_hash", sa.String(64), nullable=True),
            sa.Column("evidence_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("source_run_ids_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("harness_version", sa.String(32), nullable=True),
            sa.Column("validation_status", sa.String(32), nullable=False, server_default="unvalidated"),
            sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("supersedes_id", sa.String(64), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_memory_v2_scope", "memory_v2_records", ["scope"])
        op.create_index("ix_memory_v2_key", "memory_v2_records", ["key"])
        op.create_index("ix_memory_v2_project", "memory_v2_records", ["project_id"])
        op.create_index("ix_memory_v2_session", "memory_v2_records", ["session_id"])
        op.create_index("ix_memory_v2_content_hash", "memory_v2_records", ["content_hash"])
        op.create_index("ix_memory_v2_status", "memory_v2_records", ["validation_status"])
        op.create_index("ix_memory_v2_supersedes", "memory_v2_records", ["supersedes_id"])
        op.create_index("ix_memory_v2_scope_key", "memory_v2_records", ["scope", "key"])
        op.create_index("ix_memory_v2_scope_proj", "memory_v2_records", ["scope", "project_id"])
        op.create_index("ix_memory_v2_scope_sess", "memory_v2_records", ["scope", "session_id"])
        op.create_index("ix_memory_v2_status_conf", "memory_v2_records", ["validation_status", "confidence"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "memory_v2_records" in existing:
        op.drop_table("memory_v2_records")
