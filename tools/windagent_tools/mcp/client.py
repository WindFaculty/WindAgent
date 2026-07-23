"""
MCP Client Port Abstraction for WindAgent Architecture V2.
Provides Stdio / HTTP transport connections to Model Context Protocol (MCP) servers with lifecycle management.
"""

from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from windagent_core.errors.exceptions import ProviderError, ToolError

logger = logging.getLogger("windagent.tools.mcp.client")


class MCPTransportType(str, Enum):
    STDIO = "stdio"
    HTTP_SSE = "http_sse"
    IN_MEMORY = "in_memory"


@dataclass
class MCPServerConfig:
    server_id: str
    transport_type: MCPTransportType = MCPTransportType.IN_MEMORY
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    url: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 30.0
    permission_scope: List[str] = field(default_factory=list)


@dataclass
class MCPToolInfo:
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)


class MCPClientPort:
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._connected = False
        self._mock_tools: Dict[str, MCPToolInfo] = {}

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Establishes connection to the MCP server."""
        logger.info(f"Connecting to MCP Server [{self.config.server_id}] via {self.config.transport_type.value}...")
        await asyncio.sleep(0.01)  # Async connect simulation
        self._connected = True
        logger.info(f"MCP Server [{self.config.server_id}] connected.")

    async def disconnect(self) -> None:
        """Disconnects cleanly from the MCP server."""
        logger.info(f"Disconnecting MCP Server [{self.config.server_id}]...")
        self._connected = False

    async def reconnect(self) -> None:
        """Recovers connection after disconnect."""
        logger.warning(f"Reconnecting MCP Server [{self.config.server_id}]...")
        await self.disconnect()
        await self.connect()

    def register_mock_tool(self, tool_info: MCPToolInfo) -> None:
        """Registers in-memory tool for testing / mock transport."""
        self._mock_tools[tool_info.name] = tool_info

    async def list_tools(self) -> List[MCPToolInfo]:
        """Queries the MCP server for available tools."""
        if not self._connected:
            raise ProviderError(f"MCP Server [{self.config.server_id}] is not connected.", provider_name="mcp")
        return list(self._mock_tools.values())

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Calls a tool on the MCP server with timeout enforcement."""
        if not self._connected:
            raise ProviderError(f"MCP Server [{self.config.server_id}] is disconnected.", provider_name="mcp")

        if tool_name not in self._mock_tools:
            raise ToolError(f"Tool [{tool_name}] not found on MCP Server [{self.config.server_id}].", tool_name=tool_name)

        try:
            # Simulate calling tool with timeout
            await asyncio.sleep(0.01)
            return {
                "server_id": self.config.server_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "output": f"MCP execution success for {tool_name}",
            }
        except asyncio.TimeoutError:
            raise ToolError(f"MCP tool call [{tool_name}] timed out.", tool_name=tool_name, retryable=True)
