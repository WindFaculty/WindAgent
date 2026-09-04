"""SQLAlchemy table definitions for the Quality module."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String, Table, Text

from windagent.platform.persistence.metadata import metadata

quality_datasets_table = Table(
    "quality_datasets",
    metadata,
    Column("dataset_id", String(36), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("domain", String(100), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("version", String(50), nullable=False, default="1.0.0"),
    Column("metadata_json", Text, nullable=False, default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_quality_datasets_domain", "domain"),
)

quality_test_cases_table = Table(
    "quality_test_cases",
    metadata,
    Column("case_id", String(36), primary_key=True),
    Column("dataset_id", String(36), nullable=False),
    Column("name", String(200), nullable=False),
    Column("dimension", String(50), nullable=False),
    Column("input_payload_json", Text, nullable=False, default="{}"),
    Column("expected_output_json", Text, nullable=False, default="{}"),
    Column("tags_json", Text, nullable=False, default="[]"),
    Column("criteria_json", Text, nullable=False, default="[]"),
    Column("metadata_json", Text, nullable=False, default="{}"),
    Index("ix_quality_test_cases_ds", "dataset_id"),
)

quality_evaluation_runs_table = Table(
    "quality_evaluation_runs",
    metadata,
    Column("run_id", String(36), primary_key=True),
    Column("execution_id", String(100), nullable=False),
    Column("dataset_id", String(36), nullable=True),
    Column("evaluator_version", String(50), nullable=False, default="2.0.0"),
    Column("status", String(50), nullable=False, default="PENDING"),
    Column("composite_score", Float, nullable=False, default=0.0),
    Column("passed", Boolean, nullable=False, default=False),
    Column("metadata_json", Text, nullable=False, default="{}"),
    Column("optimistic_version", Integer, nullable=False, default=1),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_quality_evaluation_runs_exec", "execution_id"),
    Index("ix_quality_evaluation_runs_status", "status"),
)

quality_evaluation_records_table = Table(
    "quality_evaluation_records",
    metadata,
    Column("evaluation_id", String(36), primary_key=True),
    Column("run_id", String(36), nullable=False),
    Column("execution_id", String(100), nullable=False),
    Column("dimension", String(50), nullable=False),
    Column("metric_name", String(100), nullable=False),
    Column("score", Float, nullable=False, default=0.0),
    Column("threshold", Float, nullable=False, default=0.7),
    Column("confidence", Float, nullable=False, default=1.0),
    Column("evidence_refs_json", Text, nullable=False, default="[]"),
    Column("passed", Boolean, nullable=False, default=False),
    Column("blocked", Boolean, nullable=False, default=False),
    Column("details_json", Text, nullable=False, default="{}"),
    Column("evaluator_version", String(50), nullable=False, default="2.0.0"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_quality_evaluation_records_run", "run_id"),
    Index("ix_quality_evaluation_records_dim", "dimension"),
)

quality_verification_reports_table = Table(
    "quality_verification_reports",
    metadata,
    Column("report_id", String(36), primary_key=True),
    Column("suite_id", String(100), nullable=False),
    Column("target_id", String(100), nullable=False),
    Column("overall_status", String(50), nullable=False),
    Column("passed_gates_json", Text, nullable=False, default="[]"),
    Column("failed_gates_json", Text, nullable=False, default="[]"),
    Column("blocked_gates_json", Text, nullable=False, default="[]"),
    Column("gate_results_json", Text, nullable=False, default="[]"),
    Column("blocker_reasons_json", Text, nullable=False, default="[]"),
    Column("recommendations_json", Text, nullable=False, default="[]"),
    Column("duration_ms", Float, nullable=False, default=0.0),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_quality_verification_reports_target", "target_id"),
)

quality_baseline_comparisons_table = Table(
    "quality_baseline_comparisons",
    metadata,
    Column("comparison_id", String(36), primary_key=True),
    Column("candidate_id", String(100), nullable=False),
    Column("baseline_id", String(100), nullable=False),
    Column("evaluator_version", String(50), nullable=False, default="2.0.0"),
    Column("composite_candidate_score", Float, nullable=False, default=0.0),
    Column("composite_baseline_score", Float, nullable=False, default=0.0),
    Column("composite_delta", Float, nullable=False, default=0.0),
    Column("regression_detected", Boolean, nullable=False, default=False),
    Column("passed", Boolean, nullable=False, default=False),
    Column("metric_deltas_json", Text, nullable=False, default="[]"),
    Column("metadata_json", Text, nullable=False, default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_quality_baseline_candidate", "candidate_id"),
    Index("ix_quality_baseline_baseline", "baseline_id"),
)
