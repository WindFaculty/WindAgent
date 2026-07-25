"""Canonical Tool Port Protocols for WindAgent Core contracts (Phase 5)."""

from __future__ import annotations
from typing import Optional, Protocol, runtime_checkable

from windagent_core.contracts.tools.invocation import ToolInvocation
from windagent_core.contracts.tools.metadata import (
    ToolDefinition,
    ToolExecutionContext,
)
from windagent_core.contracts.tools.results import ToolResult


@runtime_checkable
class ToolExecutorPort(Protocol):
    """Port implemented by executable tool adapters."""

    @property
    def definition(self) -> ToolDefinition:
        ...

    async def execute(
        self, invocation: ToolInvocation, ctx: ToolExecutionContext
    ) -> ToolResult:
        ...


@runtime_checkable
class ToolRegistryPort(Protocol):
    """Port for tool discovery and lookup."""

    def get(self, name: str) -> Optional[ToolExecutorPort]:
        ...

    def list_definitions(self) -> list[ToolDefinition]:
        ...
