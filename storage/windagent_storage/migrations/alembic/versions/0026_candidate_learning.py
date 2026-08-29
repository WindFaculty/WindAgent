"""0026 Candidate Learning and Learned Rules (Phase 9) - ban_ke_hoach_v1 §14, §23, §24."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0026_candidate_learning"
down_revision = "0025_experience_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "learning_candidates" not in existing:
        op.create_table(
            "learning_candidates",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("condition", sa.Text(), nullable=False),
            sa.Column("proposed_change_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("reasoning_summary", sa.Text(), nullable=False),
            sa.Column("supporting_experiences_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("counter_evidence_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("sample_size", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("scope", sa.String(32), nullable=False, server_default="project"),
            sa.Column("risk_level", sa.String(32), nullable=False, server_default="medium"),
            sa.Column("status", sa.String(32), nullable=False, server_default="proposed"),
            sa.Column("project_id", sa.String(64), nullable=True),
            sa.Column("domain", sa.String(64), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_learning_candidates_status", "learning_candidates", ["status"])
        op.create_index("ix_learning_candidates_project_id", "learning_candidates", ["project_id"])
        op.create_index("ix_learning_candidates_domain", "learning_candidates", ["domain"])
        op.create_index("ix_learning_candidates_kind", "learning_candidates", ["kind"])
        op.create_index("ix_candidate_status_conf", "learning_candidates", ["status", "confidence"])
        op.create_index("ix_candidate_proj_status", "learning_candidates", ["project_id", "status"])
        op.create_index("ix_candidate_domain_status", "learning_candidates", ["domain", "status"])
        op.create_index("ix_candidate_kind_status", "learning_candidates", ["kind", "status"])
        op.create_index("ix_candidate_created_at", "learning_candidates", ["created_at"])

    if "learned_rules" not in existing:
        op.create_table(
            "learned_rules",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("condition", sa.Text(), nullable=False),
            sa.Column("recommendation", sa.Text(), nullable=False),
            sa.Column("domain", sa.String(64), nullable=False, server_default="general"),
            sa.Column("scope", sa.String(32), nullable=False, server_default="project"),
            sa.Column("evidence_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("sample_size", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("harness_version", sa.String(64), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("state", sa.String(32), nullable=False, server_default="candidate"),
        )
        op.create_index("ix_learned_rules_domain", "learned_rules", ["domain"])
        op.create_index("ix_learned_rules_state", "learned_rules", ["state"])
        op.create_index("ix_rule_domain_state", "learned_rules", ["domain", "state"])
        op.create_index("ix_rule_created_at", "learned_rules", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "learned_rules" in existing:
        op.drop_table("learned_rules")
    if "learning_candidates" in existing:
        op.drop_table("learning_candidates")

