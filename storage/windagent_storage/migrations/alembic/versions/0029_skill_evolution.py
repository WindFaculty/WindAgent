"""0029 Skill Evolution and Versioning (Phase 12) - ban_ke_hoach_v1 §18, §24, §25."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0029_skill_evolution"
down_revision = "0028_experiment_promotion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "skill_candidates" not in existing:
        op.create_table(
            "skill_candidates",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("skill_id", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="proposed"),
            sa.Column("risk_level", sa.String(32), nullable=False, server_default="low"),
            sa.Column("is_executable", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("is_high_risk", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("proposed_manifest_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("proposed_code", sa.Text(), nullable=True),
            sa.Column("reasoning_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("supporting_experiences_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("security_audit_json", sa.Text(), nullable=True),
            sa.Column("evaluation_json", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_skill_candidates_skill_id", "skill_candidates", ["skill_id"])
        op.create_index("ix_skill_candidates_status", "skill_candidates", ["status"])
        op.create_index("ix_skill_cand_skill_status", "skill_candidates", ["skill_id", "status"])
        op.create_index("ix_skill_cand_created_at", "skill_candidates", ["created_at"])

    if "skill_versions" not in existing:
        op.create_table(
            "skill_versions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("skill_id", sa.String(64), nullable=False),
            sa.Column("version", sa.String(32), nullable=False),
            sa.Column("parent_version", sa.String(64), nullable=True),
            sa.Column("manifest_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("code_hash", sa.String(64), nullable=True),
            sa.Column("source_code", sa.Text(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("promoted_from_candidate_id", sa.String(64), nullable=True),
            sa.Column("security_audit_id", sa.String(64), nullable=True),
            sa.Column("evaluation_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_skill_versions_skill_id", "skill_versions", ["skill_id"])
        op.create_index("ix_skill_versions_version", "skill_versions", ["version"])
        op.create_index("ix_skill_versions_status", "skill_versions", ["status"])
        op.create_index("ix_skill_versions_promoted_from_candidate_id", "skill_versions", ["promoted_from_candidate_id"])
        op.create_index("ix_skill_ver_skill_status", "skill_versions", ["skill_id", "status"])
        op.create_index("ix_skill_ver_skill_version", "skill_versions", ["skill_id", "version"])
        op.create_index("ix_skill_ver_created_at", "skill_versions", ["created_at"])

    if "skill_promotion_decisions" not in existing:
        op.create_table(
            "skill_promotion_decisions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("candidate_id", sa.String(64), nullable=False),
            sa.Column("skill_id", sa.String(64), nullable=False),
            sa.Column("source_version", sa.String(32), nullable=True),
            sa.Column("target_version", sa.String(32), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending_approval"),
            sa.Column("security_audit_passed", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("evaluation_passed", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("requires_human_approval", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("approved_by", sa.String(64), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("decision_rationale", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_skill_promotion_decisions_candidate_id", "skill_promotion_decisions", ["candidate_id"])
        op.create_index("ix_skill_promotion_decisions_skill_id", "skill_promotion_decisions", ["skill_id"])
        op.create_index("ix_skill_promotion_decisions_status", "skill_promotion_decisions", ["status"])
        op.create_index("ix_skill_prom_skill_status", "skill_promotion_decisions", ["skill_id", "status"])
        op.create_index("ix_skill_prom_cand_status", "skill_promotion_decisions", ["candidate_id", "status"])
        op.create_index("ix_skill_prom_created_at", "skill_promotion_decisions", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "skill_promotion_decisions" in existing:
        op.drop_table("skill_promotion_decisions")
    if "skill_versions" in existing:
        op.drop_table("skill_versions")
    if "skill_candidates" in existing:
        op.drop_table("skill_candidates")

