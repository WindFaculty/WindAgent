"""0030 Subagent Evolution and Versioning (Phase 13) - ban_ke_hoach_v1 §19, §24, §25."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0030_subagent_evolution"
down_revision = "0029_skill_evolution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "subagent_candidates" not in existing:
        op.create_table(
            "subagent_candidates",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("role", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="proposed"),
            sa.Column("risk_level", sa.String(32), nullable=False, server_default="low"),
            sa.Column("is_high_risk", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("proposed_spec_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("reasoning_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("supporting_experiences_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("security_audit_json", sa.Text(), nullable=True),
            sa.Column("evaluation_json", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_subagent_candidates_role", "subagent_candidates", ["role"])
        op.create_index("ix_subagent_candidates_status", "subagent_candidates", ["status"])
        op.create_index("ix_subagent_cand_role_status", "subagent_candidates", ["role", "status"])
        op.create_index("ix_subagent_cand_created_at", "subagent_candidates", ["created_at"])

    if "subagent_spec_versions" not in existing:
        op.create_table(
            "subagent_spec_versions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("role", sa.String(64), nullable=False),
            sa.Column("version", sa.String(32), nullable=False),
            sa.Column("parent_version", sa.String(64), nullable=True),
            sa.Column("objective", sa.Text(), nullable=False, server_default=""),
            sa.Column("system_supplement", sa.Text(), nullable=False, server_default=""),
            sa.Column("allowed_tools_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("allowed_skills_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("model_routing_policy_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("memory_access_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("max_budget_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("max_depth", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("output_contract_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("risk_level", sa.String(32), nullable=False, server_default="low"),
            sa.Column("spec_hash", sa.String(64), nullable=True),
            sa.Column("promoted_from_candidate_id", sa.String(64), nullable=True),
            sa.Column("security_audit_id", sa.String(64), nullable=True),
            sa.Column("evaluation_id", sa.String(64), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_subagent_spec_versions_role", "subagent_spec_versions", ["role"])
        op.create_index("ix_subagent_spec_versions_version", "subagent_spec_versions", ["version"])
        op.create_index("ix_subagent_spec_versions_status", "subagent_spec_versions", ["status"])
        op.create_index("ix_subagent_spec_role_status", "subagent_spec_versions", ["role", "status"])
        op.create_index("ix_subagent_spec_role_version", "subagent_spec_versions", ["role", "version"])
        op.create_index("ix_subagent_spec_created_at", "subagent_spec_versions", ["created_at"])

    if "subagent_promotion_decisions" not in existing:
        op.create_table(
            "subagent_promotion_decisions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("candidate_id", sa.String(64), nullable=False),
            sa.Column("role", sa.String(64), nullable=False),
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
        op.create_index("ix_subagent_promotion_decisions_candidate_id", "subagent_promotion_decisions", ["candidate_id"])
        op.create_index("ix_subagent_promotion_decisions_role", "subagent_promotion_decisions", ["role"])
        op.create_index("ix_subagent_promotion_decisions_status", "subagent_promotion_decisions", ["status"])
        op.create_index("ix_subagent_prom_role_status", "subagent_promotion_decisions", ["role", "status"])
        op.create_index("ix_subagent_prom_cand_status", "subagent_promotion_decisions", ["candidate_id", "status"])
        op.create_index("ix_subagent_prom_created_at", "subagent_promotion_decisions", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "subagent_promotion_decisions" in existing:
        op.drop_table("subagent_promotion_decisions")
    if "subagent_spec_versions" in existing:
        op.drop_table("subagent_spec_versions")
    if "subagent_candidates" in existing:
        op.drop_table("subagent_candidates")

