"""
Unit Tests for WindAgent Tool Platform (Phase 6):
- ToolRegistry & audit logging
- PathSandbox path traversal & symlink escape prevention
- SafeShellRunner command allow/deny policies & secret masking
- PermissionEngine approval requirements & principal permission enforcement
"""

import os
from pathlib import Path
import pytest

from windagent_core.domain.types import SessionId, ToolCallId
from windagent_core.contracts.tools import ToolInvocation
from windagent_core.errors.exceptions import PermissionDeniedError
from windagent_tools import (
    ToolRegistry, PermissionEngine, PathSandbox, SafeShellRunner,
    ToolExecutionContext, ReadFileTool, WriteFileTool, ExecShellTool
)


@pytest.mark.asyncio
async def test_tool_registry_and_execution(tmp_path):
    registry = ToolRegistry()
    read_tool = ReadFileTool()
    write_tool = WriteFileTool()
    registry.register_tool(read_tool)
    registry.register_tool(write_tool)

    assert len(registry.list_tools()) == 2
    assert registry.get_tool("read_file").name == "read_file"

    sid = SessionId.generate()
    ctx = ToolExecutionContext(workspace_root=str(tmp_path), session_id=sid, user_approved=True)

    # Write file test
    inv_write = ToolInvocation(id=ToolCallId.generate(), tool_name="write_file", params={"file_path": "sub/hello.txt", "content": "Hello V2 Tool Platform"})
    res_write = await write_tool.execute(inv_write, ctx)
    assert res_write.success
    registry.log_execution_audit(inv_write, res_write, ctx)

    # Read file test
    inv_read = ToolInvocation(id=ToolCallId.generate(), tool_name="read_file", params={"file_path": "sub/hello.txt"})
    res_read = await read_tool.execute(inv_read, ctx)
    assert res_read.success
    assert res_read.data["content"] == "Hello V2 Tool Platform"
    registry.log_execution_audit(inv_read, res_read, ctx)

    audit_log = registry.get_audit_log()
    assert len(audit_log) == 2


def test_path_sandbox_traversal_prevention(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("top secret data")

    sandbox = PathSandbox(workspace)

    # Normal inside path
    safe = sandbox.resolve_safe_path("docs/readme.md")
    assert safe.relative_to(workspace) == Path("docs/readme.md")

    # Path traversal attack attempting to escape workspace
    with pytest.raises(PermissionDeniedError, match="Path traversal denied"):
        sandbox.resolve_safe_path("../../secret.txt")

    with pytest.raises(PermissionDeniedError, match="Path traversal denied"):
        sandbox.resolve_safe_path(outside_file)


def test_path_sandbox_symlink_escape_prevention(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "target.txt"
    outside_file.write_text("outside data")

    # Create symlink inside workspace pointing outside
    symlink_file = workspace / "escaped_link.txt"
    try:
        os.symlink(outside_file, symlink_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not supported on this environment.")

    sandbox = PathSandbox(workspace)
    with pytest.raises(PermissionDeniedError, match="Path traversal denied"):
        sandbox.resolve_safe_path("escaped_link.txt")


@pytest.mark.asyncio
async def test_safe_shell_runner_policies(tmp_path):
    runner = SafeShellRunner(workspace_root=str(tmp_path))

    # Forbidden command pattern
    with pytest.raises(PermissionDeniedError, match="forbidden pattern"):
        runner.validate_command_policy("rm -rf /")

    # Safe command execution with secret masking
    exit_code, stdout, stderr = await runner.execute_command("echo Bearer secret_token_123456789")
    assert exit_code == 0
    assert "secret_token_123456789" not in stdout
    assert "***REDACTED_SECRET***" in stdout


@pytest.mark.asyncio
async def test_permission_engine_approval_requirements(tmp_path):
    engine = PermissionEngine(enforce_strict=True)
    shell_tool = ExecShellTool()
    sid = SessionId.generate()
    inv = ToolInvocation(id=ToolCallId.generate(), tool_name="exec_shell", params={"command": "echo test"})

    # Unapproved call to high-risk tool must fail
    ctx_unapproved = ToolExecutionContext(workspace_root=str(tmp_path), session_id=sid, user_approved=False)
    with pytest.raises(PermissionDeniedError, match="requires explicit user approval"):
        await engine.evaluate_and_enforce(shell_tool.definition, inv, ctx_unapproved)

    # Approved call succeeds permission check
    ctx_approved = ToolExecutionContext(workspace_root=str(tmp_path), session_id=sid, user_approved=True)
    await engine.evaluate_and_enforce(shell_tool.definition, inv, ctx_approved)
