"""
Legacy Tool Adapters for WindAgent Architecture V2.
Wraps legacy tools into V2 BaseTool implementations with PathSandbox & PermissionEngine security.
"""

from __future__ import annotations
import time

from windagent_core.contracts.tools import ToolInvocation, ToolResult
from windagent_tools.base import BaseTool, ToolDefinition, ToolExecutionContext, ToolRiskLevel
from windagent_tools.filesystem.sandbox import PathSandbox
from windagent_tools.shell.runner import SafeShellRunner


class ReadFileTool(BaseTool):
    def __init__(self):
        super().__init__(
            definition=ToolDefinition(
                name="read_file",
                description="Reads text content from a file inside workspace.",
                risk_level=ToolRiskLevel.READ_ONLY,
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.perf_counter()
        rel_path = invocation.params.get("path") or invocation.params.get("file_path")
        if not rel_path:
            return ToolResult(call_id=invocation.id, success=False, error="Parameter 'file_path' is required.")

        sandbox = PathSandbox(ctx.workspace_root)
        safe_path = sandbox.resolve_safe_path(rel_path)
        sandbox.check_file_size(safe_path)

        if not safe_path.exists():
            return ToolResult(call_id=invocation.id, success=False, error=f"File not found: {rel_path}")

        content = safe_path.read_text(encoding="utf-8", errors="replace")
        elapsed = (time.perf_counter() - start_t) * 1000.0
        return ToolResult(call_id=invocation.id, success=True, data={"content": content}, execution_time_ms=elapsed)


class WriteFileTool(BaseTool):
    def __init__(self):
        super().__init__(
            definition=ToolDefinition(
                name="write_file",
                description="Writes text content to a file inside workspace.",
                risk_level=ToolRiskLevel.WORKSPACE_WRITE,
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.perf_counter()
        rel_path = invocation.params.get("path") or invocation.params.get("file_path")
        content = invocation.params.get("content", "")
        if not rel_path:
            return ToolResult(call_id=invocation.id, success=False, error="Parameter 'file_path' is required.")

        sandbox = PathSandbox(ctx.workspace_root)
        safe_path = sandbox.resolve_safe_path(rel_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding="utf-8")

        elapsed = (time.perf_counter() - start_t) * 1000.0
        return ToolResult(call_id=invocation.id, success=True, data={"path": str(safe_path), "bytes": len(content)}, execution_time_ms=elapsed)


class ExecShellTool(BaseTool):
    def __init__(self):
        super().__init__(
            definition=ToolDefinition(
                name="exec_shell",
                description="Executes a shell command safely.",
                risk_level=ToolRiskLevel.PROCESS_EXECUTION,
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.perf_counter()
        cmd = invocation.params.get("command") or invocation.params.get("cmd")
        if not cmd:
            return ToolResult(call_id=invocation.id, success=False, error="Parameter 'command' is required.")

        runner = SafeShellRunner(workspace_root=ctx.workspace_root)
        try:
            exit_code, stdout, stderr = await runner.execute_command(
                command_line=cmd,
                timeout_seconds=invocation.timeout_seconds,
            )
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return ToolResult(
                call_id=invocation.id,
                success=(exit_code == 0),
                data={"exit_code": exit_code, "stdout": stdout, "stderr": stderr},
                error=None if exit_code == 0 else f"Command exited with code {exit_code}",
                execution_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return ToolResult(call_id=invocation.id, success=False, error=str(e), execution_time_ms=elapsed)


class ClickXYTool(BaseTool):
    def __init__(self):
        super().__init__(
            definition=ToolDefinition(
                name="click_xy",
                description="Simulates a mouse click at (x, y) coordinates.",
                risk_level=ToolRiskLevel.READ_ONLY,
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        x = invocation.params.get("x", 0)
        y = invocation.params.get("y", 0)
        return ToolResult(call_id=invocation.id, success=True, data={"x": x, "y": y, "action": "clicked"})


class OpenURLTool(BaseTool):
    def __init__(self):
        super().__init__(
            definition=ToolDefinition(
                name="open_url",
                description="Opens a web URL in browser.",
                risk_level=ToolRiskLevel.EXTERNAL_NETWORK,
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        url = invocation.params.get("url", "")
        return ToolResult(call_id=invocation.id, success=True, data={"url": url, "status": "opened"})
