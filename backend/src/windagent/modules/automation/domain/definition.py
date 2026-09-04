"""Tool definition domain (Phase 12).

REWRITE of frozen ``windagent_core.contracts.tools.metadata`` + ``windagent_tools.base``
but expressed as a pure V2 bounded context.  Semantics preserved:

- ``ToolRiskLevel`` values are identical to the frozen enum so parity tests
  can compare risk classification without translation.
- ``ToolDefinition`` is frozen, validates every field, and carries the
  canonical metadata contract (capability, side-effect class, idempotency,
  destructiveness, sandbox, schemas).  No implementation knowledge leaks
  into this type — it is pure data.

No legacy import appears here; this package imports only kernel primitives
and stdlib.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def _optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


class ToolRiskLevel(StrEnum):
    """Risk classification for a tool — frozen from old ``ToolRiskLevel``."""

    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    EXTERNAL_NETWORK = "external_network"
    SECRET_ACCESS = "secret_access"
    PROCESS_EXECUTION = "process_execution"
    DESTRUCTIVE = "destructive"
    PRIVILEGED = "privileged"


class RuntimeType(StrEnum):
    """Canonical runtime adapter names (plan section 18)."""

    IN_PROCESS = "in_process"
    SUBPROCESS = "subprocess"
    BROWSER = "browser"
    MCP = "mcp"
    DESKTOP = "desktop"
    CONTAINER = "container"
    REMOTE = "remote"


# Ordered sets for policy mapping
HIGH_RISK_LEVELS: frozenset[ToolRiskLevel] = frozenset(
    {
        ToolRiskLevel.EXTERNAL_NETWORK,
        ToolRiskLevel.SECRET_ACCESS,
        ToolRiskLevel.PROCESS_EXECUTION,
        ToolRiskLevel.DESTRUCTIVE,
        ToolRiskLevel.PRIVILEGED,
    }
)

# Side-effect classes preserved from frozen registry
SIDE_EFFECT_CLASSES: frozenset[str] = frozenset(
    {"none", "filesystem", "process", "network", "database", "git"}
)

# Sandbox requirements
SANDBOX_REQUIREMENTS: frozenset[str] = frozenset(
    {"none", "path_sandbox", "subprocess_sandbox", "browser_sandbox"}
)


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Immutable canonical tool metadata descriptor."""

    name: str
    description: str
    version: str = "1.0.0"
    risk_level: ToolRiskLevel = ToolRiskLevel.READ_ONLY
    capability: str = "general"
    runtime_type: RuntimeType = RuntimeType.IN_PROCESS
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required_text(self.name, "name"))
        object.__setattr__(self, "description", _required_text(self.description, "description"))
        object.__setattr__(self, "version", _required_text(self.version, "version"))
        if not isinstance(self.risk_level, ToolRiskLevel):
            raise TypeError("risk_level must be a ToolRiskLevel")
        object.__setattr__(self, "capability", _required_text(self.capability, "capability"))
        if not isinstance(self.runtime_type, RuntimeType):
            raise TypeError("runtime_type must be a RuntimeType")
        if self.side_effect_class not in SIDE_EFFECT_CLASSES:
            raise ValueError(f"side_effect_class must be one of {sorted(SIDE_EFFECT_CLASSES)}")
        if self.sandbox_requirement not in SANDBOX_REQUIREMENTS:
            raise ValueError(
                f"sandbox_requirement must be one of {sorted(SANDBOX_REQUIREMENTS)}"
            )
        if not isinstance(self.is_idempotent, bool):
            raise TypeError("is_idempotent must be a bool")
        if not isinstance(self.is_destructive, bool):
            raise TypeError("is_destructive must be a bool")
        if not isinstance(self.is_reversible, bool):
            raise TypeError("is_reversible must be a bool")
        if isinstance(self.timeout_seconds, bool) or not isinstance(
            self.timeout_seconds, (int, float)
        ):
            raise TypeError("timeout_seconds must be a number")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        object.__setattr__(self, "timeout_seconds", float(self.timeout_seconds))
        if not isinstance(self.required_permissions, tuple):
            raise TypeError("required_permissions must be a tuple")
        for perm in self.required_permissions:
            _required_text(perm, "required_permissions entry")
        if not isinstance(self.artifact_outputs, tuple):
            raise TypeError("artifact_outputs must be a tuple")
        for art in self.artifact_outputs:
            _required_text(art, "artifact_outputs entry")
        if not isinstance(self.retry_eligible, bool):
            raise TypeError("retry_eligible must be a bool")
        object.__setattr__(self, "redaction_policy", _required_text(self.redaction_policy, "redaction_policy"))
        if not isinstance(self.parameters_schema, dict):
            raise TypeError("parameters_schema must be a dict")
        if not isinstance(self.output_schema, dict):
            raise TypeError("output_schema must be a dict")
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "risk_level": self.risk_level.value,
            "capability": self.capability,
            "runtime_type": self.runtime_type.value,
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
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolDefinition:
        return cls(
            name=data["name"],
            description=data["description"],
            version=data.get("version", "1.0.0"),
            risk_level=ToolRiskLevel(data.get("risk_level", "read_only")),
            capability=data.get("capability", "general"),
            runtime_type=RuntimeType(data.get("runtime_type", "in_process")),
            side_effect_class=data.get("side_effect_class", "none"),
            is_idempotent=data.get("is_idempotent", True),
            is_destructive=data.get("is_destructive", False),
            is_reversible=data.get("is_reversible", True),
            timeout_seconds=float(data.get("timeout_seconds", 30.0)),
            required_permissions=tuple(data.get("required_permissions", ())),
            sandbox_requirement=data.get("sandbox_requirement", "none"),
            artifact_outputs=tuple(data.get("artifact_outputs", ())),
            retry_eligible=data.get("retry_eligible", True),
            redaction_policy=data.get("redaction_policy", "secrets_only"),
            parameters_schema=data.get("parameters_schema", {}),
            output_schema=data.get("output_schema", {}),
            enabled=data.get("enabled", True),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)

    @property
    def input_schema(self) -> dict[str, Any]:
        return self.parameters_schema


__all__ = [
    "HIGH_RISK_LEVELS",
    "RuntimeType",
    "SANDBOX_REQUIREMENTS",
    "SIDE_EFFECT_CLASSES",
    "ToolDefinition",
    "ToolRiskLevel",
]
