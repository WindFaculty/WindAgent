"""0027 Continual Harness V1 and Refinement Proposals (Phase 10) - ban_ke_hoach_v1 §15, §16, §24."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0027_continual_harness"
down_revision = "0026_candidate_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "harness_versions" not in existing:
        op.create_table(
            "harness_versions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("parent_version", sa.String(64), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("entries_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("diff_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("promotion_decision_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("evaluation_set_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_by", sa.String(64), nullable=False, server_default="system"),
            sa.Column("project_id", sa.String(64), nullable=True),
            sa.Column("domain", sa.String(64), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_harness_versions_status", "harness_versions", ["status"])
        op.create_index("ix_harness_versions_project_id", "harness_versions", ["project_id"])
        op.create_index("ix_harness_versions_domain", "harness_versions", ["domain"])
        op.create_index("ix_harness_versions_is_active", "harness_versions", ["is_active"])
        op.create_index("ix_harness_version_proj_active", "harness_versions", ["project_id", "is_active"])
        op.create_index("ix_harness_version_proj_status", "harness_versions", ["project_id", "status"])
        op.create_index("ix_harness_version_domain_active", "harness_versions", ["domain", "is_active"])
        op.create_index("ix_harness_version_number", "harness_versions", ["version_number"])
        op.create_index("ix_harness_version_created_at", "harness_versions", ["created_at"])

    if "refinement_proposals" not in existing:
        op.create_table(
            "refinement_proposals",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("target_harness_version", sa.String(64), nullable=False),
            sa.Column("candidate_ids_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("proposed_entries_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("preview_diff_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(32), nullable=False, server_default="preview"),
            sa.Column("evaluation_results_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("project_id", sa.String(64), nullable=True),
            sa.Column("created_by", sa.String(64), nullable=False, server_default="system"),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_refinement_proposals_status", "refinement_proposals", ["status"])
        op.create_index("ix_refinement_proposals_project_id", "refinement_proposals", ["project_id"])
        op.create_index("ix_refinements_target_version", "refinement_proposals", ["target_harness_version"])
        op.create_index("ix_refinements_proj_status", "refinement_proposals", ["project_id", "status"])
        op.create_index("ix_refinements_created_at", "refinement_proposals", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "refinement_proposals" in existing:
        op.drop_table("refinement_proposals")
    if "harness_versions" in existing:
        op.drop_table("harness_versions")

