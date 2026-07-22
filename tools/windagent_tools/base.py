"""
Base Tool Contract & Framework Models for WindAgent Architecture V2.
Declares ToolRiskLevel, ToolDefinition, ToolExecutionContext, and BaseModel.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from windagent_core.domain.types import SessionId
from windagent_core.domain.models import ToolInvocation, ToolResult
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
    name: str
    description: str
    version: str = "1.0.0"
    risk_level: ToolRiskLevel = ToolRiskLevel.READ_ONLY
    required_permissions: List[str] = field(default_factory=list)
    timeout_seconds: float = 30.0
    parameters_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecutionContext:
    workspace_root: str
    session_id: SessionId
    principal: Optional[Principal] = None
    env_vars: Dict[str, str] = field(default_factory=dict)
    user_approved: bool = False


class BaseTool(ABC):
    def __init__(self, definition: ToolDefinition):
        self.definition = definition

    @property
    def name(self) -> str:
        return self.definition.name

    @abstractmethod
    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        """Executes the tool logic under the provided execution context."""
        pass
