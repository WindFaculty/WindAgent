"""
MCP Tool Adapter for WindAgent Architecture V2.
Wraps MCP server tools into WindAgent V2 BaseTool implementations.
Mandates that every MCP tool execution is evaluated and enforced by PermissionEngine.
"""

from __future__ import annotations
import time
from typing import List

from windagent_core.domain.models import ToolInvocation, ToolResult
from windagent_tools.base import BaseTool, ToolDefinition, ToolExecutionContext, ToolRiskLevel
from windagent_tools.mcp.client import MCPClientPort, MCPToolInfo
from windagent_tools.registry import ToolRegistry
from windagent_tools.security.permission_engine import PermissionEngine


class MCPToolAdapter(BaseTool):
    def __init__(
        self,
        client: MCPClientPort,
        tool_info: MCPToolInfo,
        permission_engine: PermissionEngine,
        risk_level: ToolRiskLevel = ToolRiskLevel.EXTERNAL_NETWORK,
    ):
        prefixed_name = f"mcp_{client.config.server_id}_{tool_info.name}"
        definition = ToolDefinition(
            name=prefixed_name,
            description=f"MCP Tool [{tool_info.name}] on server [{client.config.server_id}]: {tool_info.description}",
            risk_level=risk_level,
            required_permissions=[f"mcp:{client.config.server_id}:{tool_info.name}"],
            timeout_seconds=client.config.timeout_seconds,
            parameters_schema=tool_info.input_schema,
        )
        super().__init__(definition=definition)
        self.client = client
        self.tool_info = tool_info
        self.permission_engine = permission_engine

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.perf_counter()

        # 1. Mandatory Permission Engine Security Evaluation
        await self.permission_engine.evaluate_and_enforce(
            definition=self.definition,
            invocation=invocation,
            ctx=ctx,
        )

        # 2. Invoke tool via MCP Client Port
        try:
            mcp_res = await self.client.call_tool(
                tool_name=self.tool_info.name,
                arguments=invocation.params,
            )
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return ToolResult(
                call_id=invocation.id,
                success=True,
                data=mcp_res,
                execution_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error=str(e),
                execution_time_ms=elapsed,
            )


async def register_mcp_server_tools(
    client: MCPClientPort,
    registry: ToolRegistry,
    permission_engine: PermissionEngine,
) -> List[str]:
    """Queries an MCP client and registers all its tools as MCPToolAdapters in ToolRegistry."""
    mcp_tools = await client.list_tools()
    registered_names = []

    for tool_info in mcp_tools:
        adapter = MCPToolAdapter(
            client=client,
            tool_info=tool_info,
            permission_engine=permission_engine,
        )
        registry.register_tool(adapter)
        registered_names.append(adapter.name)

    return registered_names
