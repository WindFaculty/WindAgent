"""0028 Experiment and Promotion Decisions (Phase 11) - ban_ke_hoach_v1 §17, §24, §35."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0028_experiment_promotion"
down_revision = "0027_continual_harness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "experiments" not in existing:
        op.create_table(
            "experiments",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("candidate_id", sa.String(64), nullable=False),
            sa.Column("baseline_harness_version", sa.String(64), nullable=False),
            sa.Column("experiment_type", sa.String(32), nullable=False, server_default="replay"),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("dataset_id", sa.String(64), nullable=True),
            sa.Column("sample_size", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("baseline_metrics_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("candidate_metrics_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("comparison_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("safety_check_passed", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("reliability_check_passed", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("verdict", sa.String(32), nullable=False, server_default="inconclusive"),
            sa.Column("project_id", sa.String(64), nullable=True),
            sa.Column("domain", sa.String(64), nullable=True),
            sa.Column("created_by", sa.String(64), nullable=False, server_default="system"),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_experiments_candidate_id", "experiments", ["candidate_id"])
        op.create_index("ix_experiments_baseline_harness_version", "experiments", ["baseline_harness_version"])
        op.create_index("ix_experiments_status", "experiments", ["status"])
        op.create_index("ix_experiments_verdict", "experiments", ["verdict"])
        op.create_index("ix_experiments_project_id", "experiments", ["project_id"])
        op.create_index("ix_experiments_domain", "experiments", ["domain"])
        op.create_index("ix_experiments_candidate_status", "experiments", ["candidate_id", "status"])
        op.create_index("ix_experiments_proj_status", "experiments", ["project_id", "status"])
        op.create_index("ix_experiments_domain_verdict", "experiments", ["domain", "verdict"])
        op.create_index("ix_experiments_created_at", "experiments", ["created_at"])

    if "promotion_decisions" not in existing:
        op.create_table(
            "promotion_decisions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("candidate_id", sa.String(64), nullable=False),
            sa.Column("experiment_id", sa.String(64), nullable=True),
            sa.Column("source_harness_version", sa.String(64), nullable=False),
            sa.Column("target_harness_version", sa.String(64), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending_approval"),
            sa.Column("gate_checks_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("is_high_risk", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("requires_human_approval", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("approved_by", sa.String(64), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("decision_rationale", sa.Text(), nullable=False, server_default=""),
            sa.Column("project_id", sa.String(64), nullable=True),
            sa.Column("domain", sa.String(64), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_promotion_decisions_candidate_id", "promotion_decisions", ["candidate_id"])
        op.create_index("ix_promotion_decisions_experiment_id", "promotion_decisions", ["experiment_id"])
        op.create_index("ix_promotion_decisions_source_harness_version", "promotion_decisions", ["source_harness_version"])
        op.create_index("ix_promotion_decisions_target_harness_version", "promotion_decisions", ["target_harness_version"])
        op.create_index("ix_promotion_decisions_status", "promotion_decisions", ["status"])
        op.create_index("ix_promotion_decisions_project_id", "promotion_decisions", ["project_id"])
        op.create_index("ix_promotion_cand_status", "promotion_decisions", ["candidate_id", "status"])
        op.create_index("ix_promotion_proj_status", "promotion_decisions", ["project_id", "status"])
        op.create_index("ix_promotion_source_target", "promotion_decisions", ["source_harness_version", "target_harness_version"])
        op.create_index("ix_promotion_created_at", "promotion_decisions", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if "promotion_decisions" in existing:
        op.drop_table("promotion_decisions")
    if "experiments" in existing:
        op.drop_table("experiments")

