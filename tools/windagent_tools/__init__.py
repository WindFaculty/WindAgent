"""
WindAgent Tools Package (V2 Architecture).
Tool registry, filesystem path sandbox, safe shell runner, permission policy engine,
plugin loader, skill manager, and MCP client adapter.
"""

from windagent_tools.base import (
    ToolRiskLevel, ToolDefinition, ToolExecutionContext, BaseTool
)
from windagent_tools.registry import ToolRegistry
from windagent_tools.security.permission_engine import PermissionEngine
from windagent_tools.filesystem.sandbox import PathSandbox
from windagent_tools.shell.runner import SafeShellRunner
from windagent_tools.adapters.legacy_tools import (
    ReadFileTool, WriteFileTool, ExecShellTool, ClickXYTool, OpenURLTool
)
from windagent_tools.plugins.manifest import PluginManifest
from windagent_tools.plugins.loader import PluginLoader
from windagent_tools.skills.manifest import SkillManifest
from windagent_tools.skills.manager import SkillManager
from windagent_tools.mcp.client import (
    MCPClientPort, MCPServerConfig, MCPTransportType, MCPToolInfo
)
from windagent_tools.mcp.adapter import MCPToolAdapter, register_mcp_server_tools

__version__ = "0.3.0"

__all__ = [
    "ToolRiskLevel", "ToolDefinition", "ToolExecutionContext", "BaseTool",
    "ToolRegistry",
    "PermissionEngine",
    "PathSandbox",
    "SafeShellRunner",
    "ReadFileTool", "WriteFileTool", "ExecShellTool", "ClickXYTool", "OpenURLTool",
    "PluginManifest", "PluginLoader",
    "SkillManifest", "SkillManager",
    "MCPClientPort", "MCPServerConfig", "MCPTransportType", "MCPToolInfo",
    "MCPToolAdapter", "register_mcp_server_tools",
]
