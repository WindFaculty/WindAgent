"""Subprocess runtime adapter (Phase 12).

Executes shell commands in a subprocess sandbox.  Mirrors the frozen
``SafeShellRunner`` semantics: timeout, workspace capture, stdout/stderr
capture, and no shell injection via arguments (command is passed as a
single shell string, matching old ``exec_shell`` behavior where the
policy engine already gated the call).
"""

from __future__ import annotations

import asyncio
import time

from ...domain.invocation import ToolExecutionContext, ToolInvocation
from ...domain.result import ToolResult
from ...domain.sandbox import resolve_safe_path


class SubprocessAdapter:
    """Executes ``exec_shell`` / ``shell`` tools via asyncio subprocess."""

    runtime_type = "subprocess"

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start = time.time()
        command = invocation.params.get("command") or invocation.params.get("cmd") or invocation.params.get("shell_command")
        cwd_param = invocation.params.get("cwd")
        if not command or not str(command).strip():
            return ToolResult(call_id=invocation.call_id, success=False, error="command is required.", execution_time_ms=(time.time() - start) * 1000)

        # Resolve cwd inside workspace when provided
        cwd: str | None = None
        if cwd_param:
            try:
                cwd = str(resolve_safe_path(str(cwd_param), ctx.workspace_root))
            except Exception as ex:
                return ToolResult(call_id=invocation.call_id, success=False, error=str(ex), execution_time_ms=(time.time() - start) * 1000)
        else:
            cwd = ctx.workspace_root

        timeout = invocation.timeout_seconds or 30.0
        try:
            proc = await asyncio.create_subprocess_shell(
                str(command),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=None,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(
                    call_id=invocation.call_id,
                    success=False,
                    error=f"command timed out after {timeout}s",
                    execution_time_ms=(time.time() - start) * 1000,
                )
            stdout = stdout_b.decode("utf-8", errors="replace")
            stderr = stderr_b.decode("utf-8", errors="replace")
            exit_code = proc.returncode or 0
            success = exit_code == 0
            return ToolResult(
                call_id=invocation.call_id,
                success=success,
                data={"exit_code": exit_code, "stdout": stdout, "stderr": stderr},
                error=stderr if not success else None,
                execution_time_ms=(time.time() - start) * 1000,
            )
        except Exception as ex:
            return ToolResult(call_id=invocation.call_id, success=False, error=str(ex), execution_time_ms=(time.time() - start) * 1000)
