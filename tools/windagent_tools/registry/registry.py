"""
Canonical Tool Registry for WindAgent Architecture V2 (Phase 19).
Manages tool registration, namespace collision prevention, capability index, and deterministic audit trail.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from windagent_core.contracts.tools import ToolInvocation, ToolResult
from windagent_core.errors.exceptions import NotFoundError, ValidationError, DomainError
from windagent_tools.base import BaseTool, ToolDefinition, ToolExecutionContext

logger = logging.getLogger("windagent.tools.registry")


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._capability_index: Dict[str, List[BaseTool]] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def register_tool(self, tool: BaseTool, override_collision: bool = False) -> None:
        name = tool.definition.name
        if not name or not name.strip():
            raise ValidationError("Tool name cannot be empty.")

        if name in self._tools and not override_collision:
            raise DomainError(
                message=f"Tool namespace collision: Tool [{name}] is already registered.",
                code="WINDAGENT_ERR_TOOL_NAMESPACE_COLLISION",
                details={"tool_name": name},
            )

        self._tools[name] = tool
        
        # Index capability
        cap = tool.definition.capability or "general"
        if cap not in self._capability_index:
            self._capability_index[cap] = []
        if tool not in self._capability_index[cap]:
            self._capability_index[cap].append(tool)

        logger.info(
            f"Registered tool [{name}] (capability: {cap}, risk: {tool.definition.risk_level.value})"
        )

    def get_tool(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise NotFoundError(f"Tool [{name}] is not registered.", code="WINDAGENT_002_TOOL_NOT_FOUND")
        return self._tools[name]

    def list_tools(self) -> List[ToolDefinition]:
        return [t.definition for t in self._tools.values()]

    def list_by_capability(self, capability: str) -> List[ToolDefinition]:
        tools = self._capability_index.get(capability, [])
        return [t.definition for t in tools]

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

    def log_execution_audit(self, invocation: ToolInvocation, result: ToolResult, ctx: ToolExecutionContext) -> None:
        audit_entry = {
            "call_id": str(invocation.id),
            "tool_name": invocation.tool_name,
            "session_id": str(ctx.session_id),
            "success": result.success,
            "execution_time_ms": result.execution_time_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._audit_log.append(audit_entry)

    async def close(self) -> None:
        """Closes registered tools and releases any active resources."""
        for tool in self._tools.values():
            if hasattr(tool, "close") and callable(getattr(tool, "close")):
                res = tool.close()
                if hasattr(res, "__await__"):
                    await res  # type: ignore[misc]

