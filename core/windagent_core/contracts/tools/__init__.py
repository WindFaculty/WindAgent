"""Canonical Tool contracts for WindAgent Core (Phase 5).

Core owns the invocation/result contract, ports, and implementation-independent
metadata. The tools package owns implementations, sandboxing, and execution.
"""

from windagent_core.contracts.tools.invocation import ToolInvocation
from windagent_core.contracts.tools.results import ToolResult
from windagent_core.contracts.tools.metadata import (
    ToolDefinition,
    ToolExecutionContext,
    ToolRiskLevel,
)
from windagent_core.contracts.tools.ports import (
    ToolExecutorPort,
    ToolRegistryPort,
)

__all__ = [
    "ToolInvocation",
    "ToolResult",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolRiskLevel",
    "ToolExecutorPort",
    "ToolRegistryPort",
]
