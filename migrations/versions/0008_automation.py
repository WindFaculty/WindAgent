"""Automation bounded context tables (Phase 12).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_tools",
        sa.Column("tool_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("risk_level", sa.String(length=50), nullable=False),
        sa.Column("capability", sa.String(length=100), nullable=False),
        sa.Column("runtime_type", sa.String(length=50), nullable=False),
        sa.Column("side_effect_class", sa.String(length=50), nullable=False),
        sa.Column("is_idempotent", sa.Boolean(), nullable=False),
        sa.Column("is_destructive", sa.Boolean(), nullable=False),
        sa.Column("is_reversible", sa.Boolean(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("required_permissions_json", sa.Text(), nullable=False),
        sa.Column("sandbox_requirement", sa.String(length=50), nullable=False),
        sa.Column("artifact_outputs_json", sa.Text(), nullable=False),
        sa.Column("retry_eligible", sa.Boolean(), nullable=False),
        sa.Column("redaction_policy", sa.String(length=50), nullable=False),
        sa.Column("parameters_schema_json", sa.Text(), nullable=False),
        sa.Column("output_schema_json", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("optimistic_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("tool_id", name=op.f("pk_automation_tools")),
        sa.UniqueConstraint("name", name=op.f("uq_automation_tools_name")),
    )
    op.create_index(op.f("ix_automation_tools_capability"), "automation_tools", ["capability"], unique=False)
    op.create_index(op.f("ix_automation_tools_runtime_type"), "automation_tools", ["runtime_type"], unique=False)
    op.create_table(
        "automation_tool_runs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("tool_version", sa.String(length=50), nullable=False),
        sa.Column("invocation_id", sa.String(length=80), nullable=False),
        sa.Column("params_json", sa.Text(), nullable=False),
        sa.Column("workspace_root", sa.String(length=500), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=True),
        sa.Column("causation_id", sa.String(length=36), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("runtime_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=False),
        sa.Column("policy_decision_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_automation_tool_runs")),
    )
    op.create_index(op.f("ix_automation_tool_runs_tool_name"), "automation_tool_runs", ["tool_name"], unique=False)
    op.create_index(op.f("ix_automation_tool_runs_status"), "automation_tool_runs", ["status"], unique=False)
    op.create_index(op.f("ix_automation_tool_runs_invocation_id"), "automation_tool_runs", ["invocation_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_automation_tool_runs_invocation_id"), table_name="automation_tool_runs")
    op.drop_index(op.f("ix_automation_tool_runs_status"), table_name="automation_tool_runs")
    op.drop_index(op.f("ix_automation_tool_runs_tool_name"), table_name="automation_tool_runs")
    op.drop_table("automation_tool_runs")
    op.drop_index(op.f("ix_automation_tools_runtime_type"), table_name="automation_tools")
    op.drop_index(op.f("ix_automation_tools_capability"), table_name="automation_tools")
    op.drop_table("automation_tools")
