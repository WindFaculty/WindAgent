"""Application view models and durable row types for Automation.

Rows are transport-neutral storage shapes; views are the application surface
returned through the command/query buses.  Both stay plain dataclasses so the
domain never owns SQL concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Durable rows (1:1 with tables)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ToolRow:
    tool_id: str
    name: str
    description: str
    version: str
    risk_level: str
    capability: str
    runtime_type: str
    side_effect_class: str
    is_idempotent: bool
    is_destructive: bool
    is_reversible: bool
    timeout_seconds: int
    required_permissions_json: str
    sandbox_requirement: str
    artifact_outputs_json: str
    retry_eligible: bool
    redaction_policy: str
    parameters_schema_json: str
    output_schema_json: str
    enabled: bool
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int


@dataclass(frozen=True, slots=True)
class ToolRunRow:
    run_id: str
    tool_name: str
    tool_version: str
    invocation_id: str
    params_json: str
    workspace_root: str
    actor_id: str | None
    correlation_id: str | None
    causation_id: str | None
    trace_id: str | None
    runtime_type: str
    status: str
    result_json: str | None
    error: str | None
    execution_time_ms: int
    policy_decision_json: str | None
    created_at: datetime | None
    completed_at: datetime | None


# --------------------------------------------------------------------------- #
# View DTOs
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ToolView:
    tool_id: str
    name: str
    description: str
    version: str
    risk_level: str
    capability: str
    runtime_type: str
    side_effect_class: str
    is_idempotent: bool
    is_destructive: bool
    is_reversible: bool
    timeout_seconds: int
    required_permissions: tuple[str, ...]
    sandbox_requirement: str
    artifact_outputs: tuple[str, ...]
    retry_eligible: bool
    redaction_policy: str
    parameters_schema: dict[str, Any]
    output_schema: dict[str, Any]
    enabled: bool
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "risk_level": self.risk_level,
            "capability": self.capability,
            "runtime_type": self.runtime_type,
            "side_effect_class": self.side_effect_class,
            "is_idempotent": self.is_idempotent,
            "is_destructive": self.is_destructive,
            "is_reversible": self.is_reversible,
            "timeout_seconds": self.timeout_seconds,
            "required_permissions": list(self.required_permissions),
            "sandbox_requirement": self.sandbox_requirement,
            "artifact_outputs": list(self.artifact_outputs),
            "retry_eligible": self.retry_eligible,
            "redaction_policy": self.redaction_policy,
            "parameters_schema": self.parameters_schema,
            "output_schema": self.output_schema,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
        }


@dataclass(frozen=True, slots=True)
class ToolRunView:
    run_id: str
    tool_name: str
    tool_version: str
    invocation_id: str
    params: dict[str, Any]
    workspace_root: str
    actor_id: str | None
    correlation_id: str | None
    causation_id: str | None
    trace_id: str | None
    runtime_type: str
    status: str
    result: Any | None
    error: str | None
    execution_time_ms: int
    policy_decision: dict[str, Any] | None
    created_at: datetime | None
    completed_at: datetime | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "invocation_id": self.invocation_id,
            "params": self.params,
            "workspace_root": self.workspace_root,
            "actor_id": self.actor_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "trace_id": self.trace_id,
            "runtime_type": self.runtime_type,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "policy_decision": self.policy_decision,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
