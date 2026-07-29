"""Shared registration factory for WindAgent's built-in runtime tools."""

from __future__ import annotations

from windagent_tools.ast import ASTSymbolExtractorTool
from windagent_tools.browser import ClickXYTool, OpenURLTool
from windagent_tools.code_search import CodeSearchTool
from windagent_tools.database import DatabaseQueryTool
from windagent_tools.filesystem import ReadFileTool, WriteFileTool
from windagent_tools.git import GitTool
from windagent_tools.github import GitHubTool
from windagent_tools.lsp import LSPTool
from windagent_tools.registry import ToolRegistry
from windagent_tools.shell import ExecShellTool
from windagent_tools.testing import TestRunnerTool


def create_builtin_tool_registry() -> ToolRegistry:
    """Create the canonical built-in registry used by runtime entrypoints."""
    registry = ToolRegistry()
    for tool in (
        ReadFileTool(),
        WriteFileTool(),
        ExecShellTool(),
        CodeSearchTool(),
        GitTool(),
        ASTSymbolExtractorTool(),
        LSPTool(),
        TestRunnerTool(),
        OpenURLTool(),
        ClickXYTool(),
        DatabaseQueryTool(),
        GitHubTool(),
    ):
        registry.register_tool(tool)
    return registry
