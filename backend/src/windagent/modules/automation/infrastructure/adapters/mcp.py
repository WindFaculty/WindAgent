"""MCP runtime adapter (Phase 12).

Stub for the Model Context Protocol adapter.  In production this will
invoke an MCP server over stdio/SSE and normalize the response using the
provider protocol pattern.  For the foundation it validates configuration
and returns a deterministic payload.
"""

from __future__ import annotations

import time

from ...domain.invocation import ToolExecutionContext, ToolInvocation
from ...domain.result import ToolResult


class McpAdapter:
    """Deterministic MCP adapter (offline)."""

    runtime_type = "mcp"

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start = time.time()
        server = invocation.params.get("mcp_server") or invocation.params.get("server") or "default"
        tool = invocation.params.get("mcp_tool") or invocation.tool_name
        if not str(tool).strip():
            return ToolResult(call_id=invocation.call_id, success=False, error="mcp_tool is required.", execution_time_ms=(time.time() - start) * 1000)
        return ToolResult(
            call_id=invocation.call_id,
            success=True,
            data={
                "runtime": "mcp",
                "server": server,
                "tool": tool,
                "params": invocation.params,
                "note": "MCP adapter simulation — real stdio/SSE transport deferred",
            },
            execution_time_ms=(time.time() - start) * 1000,
        )
