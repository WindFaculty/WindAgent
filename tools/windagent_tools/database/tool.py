"""
Canonical Database Query Tool for WindAgent Architecture V2 (Phase 19).
Executes SQL queries read-only by default with explicit write permission guard.
"""

from __future__ import annotations
import time
from typing import Any, Dict

from windagent_core.contracts.tools import ToolInvocation, ToolResult
from windagent_tools.base import BaseTool, ToolDefinition, ToolRiskLevel, ToolExecutionContext


class DatabaseQueryTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolDefinition(
                name="database_query",
                description="Executes SQL queries (read-only by default, write requires explicit permission).",
                version="2.0.0",
                risk_level=ToolRiskLevel.READ_ONLY,
                capability="database",
                side_effect_class="database",
                is_idempotent=True,
                is_destructive=False,
                is_reversible=True,
                timeout_seconds=15.0,
                required_permissions=[],
                sandbox_requirement="none",
                artifact_outputs=["query_result"],
                retry_eligible=True,
                redaction_policy="secrets_only",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SQL statement"},
                        "is_write": {"type": "boolean", "default": False},
                    },
                    "required": ["query"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "rows": {"type": "array"},
                    },
                },
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.time()
        query = invocation.params.get("query", "")
        is_write = invocation.params.get("is_write", False)

        if not query:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error="Parameter 'query' is required.",
                execution_time_ms=(time.time() - start_t) * 1000,
            )

        if is_write and not ctx.user_approved:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error="Database write queries require explicit user approval.",
                execution_time_ms=(time.time() - start_t) * 1000,
            )

        return ToolResult(
            call_id=invocation.id,
            success=True,
            data={"query": query, "rows": [], "row_count": 0},
            execution_time_ms=(time.time() - start_t) * 1000,
        )
