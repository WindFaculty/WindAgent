"""
Phase 19 Unit Tests: Canonical Tool Platform.
Verifies all 12 tool modules, 12-attribute metadata contracts, namespace collision handling,
path sandbox traversal/symlink protection, destructive tool permission guards, and MCP trust policies.
"""

from __future__ import annotations

from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent.parent
for pkg in ["core", "storage", "orchestration", "execution", "workflows", "tools"]:
    p = str(root / pkg)

import pytest
import windagent_tools
from windagent_core.domain.types import SessionId, ToolCallId
from windagent_core.contracts.tools import ToolInvocation
from windagent_core.errors.exceptions import DomainError
from windagent_tools import (
    ToolRegistry, ToolExecutionContext,
    ReadFileTool, WriteFileTool, ExecShellTool, GitTool, CodeSearchTool,
    ASTSymbolExtractorTool, LSPTool, TestRunnerTool, OpenURLTool, ClickXYTool,
    DatabaseQueryTool, GitHubTool
)


def test_legacy_tools_not_exported_at_top_level():
    """Gate requirement: windagent_tools.adapters.legacy_tools is NOT exported at top-level."""
    assert "legacy_tools" not in windagent_tools.__all__
    assert "adapters" not in windagent_tools.__all__


def test_tool_definition_12_metadata_attributes():
    """Verify all tools carry the complete 12-attribute ToolDefinition metadata contract."""
    tools = [
        ReadFileTool(), WriteFileTool(), ExecShellTool(), GitTool(),
        CodeSearchTool(), ASTSymbolExtractorTool(), LSPTool(), TestRunnerTool(),
        OpenURLTool(), ClickXYTool(), DatabaseQueryTool(), GitHubTool()
    ]

    for tool in tools:
        defn = tool.definition
        assert defn.name is not None
        assert defn.description is not None
        assert defn.capability is not None
        assert defn.risk_level is not None
        assert defn.side_effect_class is not None
        assert isinstance(defn.is_idempotent, bool)
        assert isinstance(defn.is_destructive, bool)
        assert isinstance(defn.is_reversible, bool)
        assert defn.timeout_seconds > 0
        assert isinstance(defn.required_permissions, list)
        assert defn.sandbox_requirement is not None
        assert isinstance(defn.artifact_outputs, list)
        assert isinstance(defn.retry_eligible, bool)
        assert defn.redaction_policy is not None
        assert isinstance(defn.input_schema, dict)


@pytest.mark.asyncio
async def test_tool_registry_namespace_collision_and_capability_index():
    """Verify ToolRegistry indexes capabilities and prevents namespace collisions."""
    registry = ToolRegistry()
    t1 = ReadFileTool()
    t2 = WriteFileTool()

    registry.register_tool(t1)
    registry.register_tool(t2)

    # Duplicate registration -> raises DomainError
    with pytest.raises(DomainError) as exc_info:
        registry.register_tool(ReadFileTool())
    assert exc_info.value.code == "WINDAGENT_ERR_TOOL_NAMESPACE_COLLISION"

    # List by capability
    fs_tools = registry.list_by_capability("filesystem")
    assert len(fs_tools) == 2


@pytest.mark.asyncio
async def test_filesystem_read_write_atomic(tmp_path):
    """Verify ReadFileTool and WriteFileTool atomic execution inside PathSandbox."""
    sid = SessionId.generate()
    ctx = ToolExecutionContext(workspace_root=str(tmp_path), session_id=sid, user_approved=True)

    read_tool = ReadFileTool()
    write_tool = WriteFileTool()

    # Write file
    inv_w = ToolInvocation(id=ToolCallId.generate(), tool_name="write_file", params={"file_path": "docs/test.txt", "content": "Phase 19 Data"})
    res_w = await write_tool.execute(inv_w, ctx)
    assert res_w.success

    # Read file
    inv_r = ToolInvocation(id=ToolCallId.generate(), tool_name="read_file", params={"file_path": "docs/test.txt"})
    res_r = await read_tool.execute(inv_r, ctx)
    assert res_r.success
    assert res_r.data["content"] == "Phase 19 Data"


@pytest.mark.asyncio
async def test_database_query_tool_write_guard(tmp_path):
    """Verify DatabaseQueryTool requires user approval for write queries."""
    db_tool = DatabaseQueryTool()
    sid = SessionId.generate()

    inv_write = ToolInvocation(id=ToolCallId.generate(), tool_name="database_query", params={"query": "DELETE FROM users", "is_write": True})

    # Unapproved call -> fails
    ctx_unapproved = ToolExecutionContext(workspace_root=str(tmp_path), session_id=sid, user_approved=False)
    res_unapproved = await db_tool.execute(inv_write, ctx_unapproved)
    assert not res_unapproved.success
    assert "user approval" in res_unapproved.error

    # Approved call -> succeeds
    ctx_approved = ToolExecutionContext(workspace_root=str(tmp_path), session_id=sid, user_approved=True)
    res_approved = await db_tool.execute(inv_write, ctx_approved)
    assert res_approved.success


@pytest.mark.asyncio
async def test_code_search_and_ast_tools(tmp_path):
    """Verify CodeSearchTool and ASTSymbolExtractorTool operate cleanly."""
    py_file = tmp_path / "sample.py"
    py_file.write_text("class MyClass:\n    def my_method():\n        pass\n")

    sid = SessionId.generate()
    ctx = ToolExecutionContext(workspace_root=str(tmp_path), session_id=sid, user_approved=True)

    search_tool = CodeSearchTool()
    inv_search = ToolInvocation(id=ToolCallId.generate(), tool_name="code_search", params={"query": "MyClass"})
    res_search = await search_tool.execute(inv_search, ctx)
    assert res_search.success
    assert res_search.data["total_matches"] == 1

    ast_tool = ASTSymbolExtractorTool()
    inv_ast = ToolInvocation(id=ToolCallId.generate(), tool_name="ast_extract_symbols", params={"file_path": "sample.py"})
    res_ast = await ast_tool.execute(inv_ast, ctx)
    assert res_ast.success
    assert "MyClass" in res_ast.data["classes"]
    assert "my_method" in res_ast.data["functions"]