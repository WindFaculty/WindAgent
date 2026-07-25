"""Implementation-independent tool metadata schemas (Phase 5).

Core owns the metadata contract (definition, risk level, execution context);
the tools package owns implementations, sandboxing, and enforcement adapters.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from windagent_core.domain.types import SessionId
from windagent_core.security.types import Principal


class ToolRiskLevel(str, Enum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    EXTERNAL_NETWORK = "external_network"
    SECRET_ACCESS = "secret_access"
    PROCESS_EXECUTION = "process_execution"
    DESTRUCTIVE = "destructive"
    PRIVILEGED = "privileged"


@dataclass
class ToolDefinition:
    """Canonical tool metadata descriptor."""

    name: str
    description: str
    version: str = "1.0.0"
    risk_level: ToolRiskLevel = ToolRiskLevel.READ_ONLY
    capability: str = "general"
    side_effect_class: str = "none"  # none | filesystem | process | network | database | git
    is_idempotent: bool = True
    is_destructive: bool = False
    is_reversible: bool = True
    timeout_seconds: float = 30.0
    required_permissions: List[str] = field(default_factory=list)
    sandbox_requirement: str = "none"  # none | path_sandbox | subprocess_sandbox | browser_sandbox
    artifact_outputs: List[str] = field(default_factory=list)
    retry_eligible: bool = True
    redaction_policy: str = "secrets_only"  # none | secrets_only | full
    parameters_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)

    @property
    def input_schema(self) -> Dict[str, Any]:
        return self.parameters_schema


@dataclass
class ToolExecutionContext:
    """Canonical execution context passed to tool implementations."""

    workspace_root: str
    session_id: SessionId
    principal: Optional[Principal] = None
    env_vars: Dict[str, str] = field(default_factory=dict)
    user_approved: bool = False
