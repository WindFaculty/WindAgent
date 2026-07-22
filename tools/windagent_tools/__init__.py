"""
WindAgent Tools Package (V2 Architecture).
Tool registry, filesystem path sandbox, safe shell runner, and permission policy engine.
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

__version__ = "0.3.0"

__all__ = [
    "ToolRiskLevel", "ToolDefinition", "ToolExecutionContext", "BaseTool",
    "ToolRegistry",
    "PermissionEngine",
    "PathSandbox",
    "SafeShellRunner",
    "ReadFileTool", "WriteFileTool", "ExecShellTool", "ClickXYTool", "OpenURLTool",
]
