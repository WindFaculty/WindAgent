"""BaseTool ABC for WindAgent tool implementations.

Canonical metadata contracts (ToolRiskLevel, ToolDefinition,
ToolExecutionContext) live in ``windagent_core.contracts.tools.metadata``;
re-exported here so existing tool modules keep one import site.
"""

from __future__ import annotations
from abc import ABC, abstractmethod

from windagent_core.contracts.tools import (
    ToolDefinition,
    ToolExecutionContext,
    ToolInvocation,
    ToolResult,
    ToolRiskLevel,
)

__all__ = [
    "ToolRiskLevel",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolInvocation",
    "ToolResult",
    "BaseTool",
]


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
