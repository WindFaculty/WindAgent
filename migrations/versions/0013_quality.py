"""Quality bounded context tables.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quality_datasets",
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("domain", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.String(length=50), nullable=False, server_default="1.0.0"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("dataset_id", name=op.f("pk_quality_datasets")),
    )
    op.create_index(op.f("ix_quality_datasets_domain"), "quality_datasets", ["domain"], unique=False)

    op.create_table(
        "quality_test_cases",
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("dimension", sa.String(length=50), nullable=False),
        sa.Column("input_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("expected_output_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("criteria_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("case_id", name=op.f("pk_quality_test_cases")),
    )
    op.create_index(op.f("ix_quality_test_cases_ds"), "quality_test_cases", ["dataset_id"], unique=False)

    op.create_table(
        "quality_evaluation_runs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=100), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=True),
        sa.Column("evaluator_version", sa.String(length=50), nullable=False, server_default="2.0.0"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("composite_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("optimistic_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_quality_evaluation_runs")),
    )
    op.create_index(op.f("ix_quality_evaluation_runs_exec"), "quality_evaluation_runs", ["execution_id"], unique=False)
    op.create_index(op.f("ix_quality_evaluation_runs_status"), "quality_evaluation_runs", ["status"], unique=False)

    op.create_table(
        "quality_evaluation_records",
        sa.Column("evaluation_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=100), nullable=False),
        sa.Column("dimension", sa.String(length=50), nullable=False),
        sa.Column("metric_name", sa.String(length=100), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("threshold", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("evidence_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("evaluator_version", sa.String(length=50), nullable=False, server_default="2.0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("evaluation_id", name=op.f("pk_quality_evaluation_records")),
    )
    op.create_index(op.f("ix_quality_evaluation_records_run"), "quality_evaluation_records", ["run_id"], unique=False)
    op.create_index(op.f("ix_quality_evaluation_records_dim"), "quality_evaluation_records", ["dimension"], unique=False)

    op.create_table(
        "quality_verification_reports",
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("suite_id", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.String(length=100), nullable=False),
        sa.Column("overall_status", sa.String(length=50), nullable=False),
        sa.Column("passed_gates_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("failed_gates_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("blocked_gates_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("gate_results_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("blocker_reasons_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("recommendations_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("duration_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("report_id", name=op.f("pk_quality_verification_reports")),
    )
    op.create_index(op.f("ix_quality_verification_reports_target"), "quality_verification_reports", ["target_id"], unique=False)

    op.create_table(
        "quality_baseline_comparisons",
        sa.Column("comparison_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=100), nullable=False),
        sa.Column("baseline_id", sa.String(length=100), nullable=False),
        sa.Column("evaluator_version", sa.String(length=50), nullable=False, server_default="2.0.0"),
        sa.Column("composite_candidate_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("composite_baseline_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("composite_delta", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("regression_detected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("metric_deltas_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("comparison_id", name=op.f("pk_quality_baseline_comparisons")),
    )
    op.create_index(op.f("ix_quality_baseline_candidate"), "quality_baseline_comparisons", ["candidate_id"], unique=False)
    op.create_index(op.f("ix_quality_baseline_baseline"), "quality_baseline_comparisons", ["baseline_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_quality_baseline_baseline"), table_name="quality_baseline_comparisons")
    op.drop_index(op.f("ix_quality_baseline_candidate"), table_name="quality_baseline_comparisons")
    op.drop_table("quality_baseline_comparisons")

    op.drop_index(op.f("ix_quality_verification_reports_target"), table_name="quality_verification_reports")
    op.drop_table("quality_verification_reports")

    op.drop_index(op.f("ix_quality_evaluation_records_dim"), table_name="quality_evaluation_records")
    op.drop_index(op.f("ix_quality_evaluation_records_run"), table_name="quality_evaluation_records")
    op.drop_table("quality_evaluation_records")

    op.drop_index(op.f("ix_quality_evaluation_runs_status"), table_name="quality_evaluation_runs")
    op.drop_index(op.f("ix_quality_evaluation_runs_exec"), table_name="quality_evaluation_runs")
    op.drop_table("quality_evaluation_runs")

    op.drop_index(op.f("ix_quality_test_cases_ds"), table_name="quality_test_cases")
    op.drop_table("quality_test_cases")

    op.drop_index(op.f("ix_quality_datasets_domain"), table_name="quality_datasets")
    op.drop_table("quality_datasets")
