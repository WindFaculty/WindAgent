"""
WindAgent Tools Package (V2 Architecture Phase 19).
Canonical tool platform providing registry, 12 tool modules, path sandbox, safe shell runner,
permission engine, plugin loader, skill manager, and MCP client adapter.
"""

from windagent_core.version import PRODUCT_VERSION

from windagent_tools.base import (
    ToolRiskLevel, ToolDefinition, ToolExecutionContext, BaseTool
)
from windagent_tools.registry import ToolRegistry
from windagent_tools.security.permission_engine import PermissionEngine
from windagent_tools.filesystem import PathSandbox, ReadFileTool, WriteFileTool
from windagent_tools.shell import SafeShellRunner, ExecShellTool
from windagent_tools.git import GitTool
from windagent_tools.code_search import CodeSearchTool
from windagent_tools.ast import ASTSymbolExtractorTool
from windagent_tools.lsp import LSPTool
from windagent_tools.testing import TestRunnerTool
from windagent_tools.browser import (
    BrowserActionPolicy,
    BrowserHealthCheck,
    BrowserOperation,
    BrowserProfileLock,
    BrowserRuntime,
    BrowserSessionRegistry,
    ClickXYTool,
    OpenURLTool,
)
from windagent_tools.database import DatabaseQueryTool
from windagent_tools.google_flow import (
    CandidateDownloader,
    FlowImageGenerator,
    FlowImageOperation,
    FlowJobRegistry,
    FlowJobStatus,
    FlowNavigator,
    FlowProjectManager,
    FlowReconcileAction,
    FlowUiState,
    FlowUiStateMachine,
    FlowVideoGenerator,
    FlowVideoOperation,
    PreSubmitGuard,
    ReviewGate,
    SelectorCatalog,
    VideoCandidateDownloader,
    VideoInspectorPort,
    VideoOperationMapper,
)
from windagent_tools.github import GitHubTool
from windagent_tools.mcp.client import (
    MCPClientPort, MCPServerConfig, MCPTransportType, MCPToolInfo
)
from windagent_tools.mcp.adapter import MCPToolAdapter, register_mcp_server_tools

__version__ = PRODUCT_VERSION
__all__ = [
    "ToolRiskLevel", "ToolDefinition", "ToolExecutionContext", "BaseTool",
    "ToolRegistry",
    "PermissionEngine",
    "PathSandbox", "ReadFileTool", "WriteFileTool",
    "SafeShellRunner", "ExecShellTool",
    "GitTool",
    "CodeSearchTool",
    "ASTSymbolExtractorTool",
    "LSPTool",
    "TestRunnerTool",
    "OpenURLTool", "ClickXYTool",
    "BrowserRuntime", "BrowserActionPolicy", "BrowserOperation",
    "BrowserHealthCheck", "BrowserProfileLock", "BrowserSessionRegistry",
    "FlowNavigator", "FlowProjectManager", "FlowUiState",
    "FlowUiStateMachine", "SelectorCatalog",
    "FlowImageGenerator", "FlowImageOperation", "FlowJobRegistry",
    "FlowJobStatus", "FlowReconcileAction", "CandidateDownloader",
    "PreSubmitGuard", "ReviewGate",
    "FlowVideoGenerator", "FlowVideoOperation", "VideoCandidateDownloader",
    "VideoInspectorPort", "VideoOperationMapper",
    "DatabaseQueryTool",
    "GitHubTool",
    "MCPClientPort", "MCPServerConfig", "MCPTransportType", "MCPToolInfo",
    "MCPToolAdapter", "register_mcp_server_tools",
]
