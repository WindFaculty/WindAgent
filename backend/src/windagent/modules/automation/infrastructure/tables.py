"""Durable tables for the Automation bounded context (Phase 12)."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Table, Text

from windagent.platform.persistence.metadata import metadata

tools_table = Table(
    "automation_tools",
    metadata,
    Column("tool_id", String(36), primary_key=True),
    Column("name", String(100), nullable=False, unique=True),
    Column("description", Text, nullable=False, default=""),
    Column("version", String(50), nullable=False, default="1.0.0"),
    Column("risk_level", String(50), nullable=False, default="read_only"),
    Column("capability", String(100), nullable=False, default="general"),
    Column("runtime_type", String(50), nullable=False, default="in_process"),
    Column("side_effect_class", String(50), nullable=False, default="none"),
    Column("is_idempotent", Boolean, nullable=False, default=True),
    Column("is_destructive", Boolean, nullable=False, default=False),
    Column("is_reversible", Boolean, nullable=False, default=True),
    Column("timeout_seconds", Integer, nullable=False, default=30),
    Column("required_permissions_json", Text, nullable=False, default="[]"),
    Column("sandbox_requirement", String(50), nullable=False, default="none"),
    Column("artifact_outputs_json", Text, nullable=False, default="[]"),
    Column("retry_eligible", Boolean, nullable=False, default=True),
    Column("redaction_policy", String(50), nullable=False, default="secrets_only"),
    Column("parameters_schema_json", Text, nullable=False, default="{}"),
    Column("output_schema_json", Text, nullable=False, default="{}"),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("optimistic_version", Integer, nullable=False, default=0),
    Index("ix_automation_tools_capability", "capability"),
    Index("ix_automation_tools_runtime_type", "runtime_type"),
)

tool_runs_table = Table(
    "automation_tool_runs",
    metadata,
    Column("run_id", String(36), primary_key=True),
    Column("tool_name", String(100), nullable=False),
    Column("tool_version", String(50), nullable=False, default="1.0.0"),
    Column("invocation_id", String(80), nullable=False),
    Column("params_json", Text, nullable=False, default="{}"),
    Column("workspace_root", String(500), nullable=False, default=""),
    Column("actor_id", String(100), nullable=True),
    Column("correlation_id", String(36), nullable=True),
    Column("causation_id", String(36), nullable=True),
    Column("trace_id", String(64), nullable=True),
    Column("runtime_type", String(50), nullable=False, default="in_process"),
    Column("status", String(50), nullable=False, default="pending"),
    Column("result_json", Text, nullable=True),
    Column("error", Text, nullable=True),
    Column("execution_time_ms", Integer, nullable=False, default=0),
    Column("policy_decision_json", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    Index("ix_automation_tool_runs_tool_name", "tool_name"),
    Index("ix_automation_tool_runs_status", "status"),
    Index("ix_automation_tool_runs_invocation_id", "invocation_id"),
)
