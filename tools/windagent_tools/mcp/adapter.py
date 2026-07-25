"""
MCP Tool Adapter for WindAgent Architecture V2 (Phase 19).
Wraps MCP server tools into WindAgent V2 BaseTool implementations with server trust policy evaluation.
Mandates that every MCP tool execution is evaluated and enforced by PermissionEngine.
"""

from __future__ import annotations
import time
from typing import List

from windagent_core.contracts.tools import ToolInvocation, ToolResult
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
        is_trusted_server: bool = True,
    ):
        prefixed_name = f"mcp_{client.config.server_id}_{tool_info.name}"
        definition = ToolDefinition(
            name=prefixed_name,
            description=f"MCP Tool [{tool_info.name}] on server [{client.config.server_id}]: {tool_info.description}",
            risk_level=risk_level if is_trusted_server else ToolRiskLevel.DESTRUCTIVE,
            capability="mcp",
            side_effect_class="network",
            is_idempotent=False,
            is_destructive=not is_trusted_server,
            is_reversible=False,
            timeout_seconds=client.config.timeout_seconds,
            required_permissions=[f"mcp:{client.config.server_id}:{tool_info.name}"],
            sandbox_requirement="none",
            artifact_outputs=["mcp_response"],
            retry_eligible=is_trusted_server,
            redaction_policy="secrets_only",
            parameters_schema=tool_info.input_schema,
        )
        super().__init__(definition=definition)
        self.client = client
        self.tool_info = tool_info
        self.permission_engine = permission_engine
        self.is_trusted_server = is_trusted_server

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
    trusted_servers: List[str] = None,
) -> List[str]:
    """Queries an MCP client and registers all its tools as MCPToolAdapters in ToolRegistry with trust policy."""
    mcp_tools = await client.list_tools()
    registered_names = []
    is_trusted = (trusted_servers is None) or (client.config.server_id in trusted_servers)

    for tool_info in mcp_tools:
        adapter = MCPToolAdapter(
            client=client,
            tool_info=tool_info,
            permission_engine=permission_engine,
            is_trusted_server=is_trusted,
        )
        registry.register_tool(adapter)
        registered_names.append(adapter.name)

    return registered_names
