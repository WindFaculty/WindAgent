"""Immutable Automation commands (intentions with payloads)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from windagent.platform.commands import Command

from .models import ToolRunView, ToolView


@dataclass(frozen=True, slots=True)
class RegisterTool(Command[ToolView]):
    name: str
    description: str
    version: str = "1.0.0"
    risk_level: str = "read_only"
    capability: str = "general"
    runtime_type: str = "in_process"
    side_effect_class: str = "none"
    is_idempotent: bool = True
    is_destructive: bool = False
    is_reversible: bool = True
    timeout_seconds: float = 30.0
    required_permissions: tuple[str, ...] = field(default_factory=tuple)
    sandbox_requirement: str = "none"
    artifact_outputs: tuple[str, ...] = field(default_factory=tuple)
    retry_eligible: bool = True
    redaction_policy: str = "secrets_only"
    parameters_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class UpdateTool(Command[ToolView]):
    tool_id: str
    description: str | None = None
    version: str | None = None
    risk_level: str | None = None
    capability: str | None = None
    runtime_type: str | None = None
    enabled: bool | None = None
    expected_version: int | None = None


@dataclass(frozen=True, slots=True)
class DeregisterTool(Command[None]):
    tool_id: str


@dataclass(frozen=True, slots=True)
class ExecuteTool(Command[ToolRunView]):
    tool_name: str
    params: dict[str, Any] = field(default_factory=dict)
    workspace_root: str = "/tmp"
    actor_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    trace_id: str | None = None
    user_approved: bool = False
    invocation_id: str | None = None


@dataclass(frozen=True, slots=True)
class RegisterBuiltinTools(Command[tuple[ToolView, ...]]):
    """Idempotently register the canonical built-in tool catalog."""
