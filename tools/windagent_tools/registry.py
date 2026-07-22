"""
Tool Registry for WindAgent Architecture V2.
Manages tool registration, versioning, schema validation, and deterministic audit trail generation.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from windagent_core.domain.types import ToolCallId
from windagent_core.domain.models import ToolInvocation, ToolResult
from windagent_core.errors.exceptions import NotFoundError, ValidationError
from windagent_tools.base import BaseTool, ToolDefinition, ToolExecutionContext

logger = logging.getLogger("windagent.tools.registry")


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def register_tool(self, tool: BaseTool) -> None:
        name = tool.definition.name
        if not name or not name.strip():
            raise ValidationError("Tool name cannot be empty.")
        self._tools[name] = tool
        logger.info(f"Registered tool [{name}] (version: {tool.definition.version}, risk: {tool.definition.risk_level.value})")

    def get_tool(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise NotFoundError(f"Tool [{name}] is not registered.", code="WINDAGENT_002_TOOL_NOT_FOUND")
        return self._tools[name]

    def list_tools(self) -> List[ToolDefinition]:
        return [t.definition for t in self._tools.values()]

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
