"""Adapter protocol for runtime execution (Phase 12)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ...domain.invocation import ToolExecutionContext, ToolInvocation
from ...domain.result import ToolResult


@runtime_checkable
class ToolRuntimeAdapter(Protocol):
    """Executes a single tool invocation in a specific runtime."""

    @property
    def runtime_type(self) -> str:
        """Return the canonical runtime type name (e.g., 'in_process')."""

    async def execute(
        self, invocation: ToolInvocation, ctx: ToolExecutionContext
    ) -> ToolResult:
        """Execute the invocation and return a result (never raises)."""


__all__ = ["ToolRuntimeAdapter"]
