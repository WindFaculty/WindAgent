"""
Canonical Safe Shell Tool for WindAgent Architecture V2 (Phase 19).
Provides ExecShellTool with full metadata contract and SafeShellRunner execution.
"""

from __future__ import annotations
import time
from typing import Any, Dict

from windagent_core.domain.models import ToolInvocation, ToolResult
from windagent_tools.base import BaseTool, ToolDefinition, ToolRiskLevel, ToolExecutionContext
from windagent_tools.shell.runner import SafeShellRunner


class ExecShellTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolDefinition(
                name="exec_shell",
                description="Executes a shell command safely within workspace root with policy enforcement.",
                version="2.0.0",
                risk_level=ToolRiskLevel.PROCESS_EXECUTION,
                capability="shell",
                side_effect_class="process",
                is_idempotent=False,
                is_destructive=True,
                is_reversible=False,
                timeout_seconds=30.0,
                required_permissions=["process_execution"],
                sandbox_requirement="subprocess_sandbox",
                artifact_outputs=["stdout", "stderr"],
                retry_eligible=False,
                redaction_policy="full",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command string to execute"},
                        "cwd": {"type": "string", "description": "Optional working directory"},
                    },
                    "required": ["command"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "exit_code": {"type": "integer"},
                        "stdout": {"type": "string"},
                        "stderr": {"type": "string"},
                    },
                },
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.time()
        command = invocation.params.get("command") or invocation.params.get("cmd")
        cwd = invocation.params.get("cwd")

        if not command:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error="Parameter 'command' is required.",
                execution_time_ms=(time.time() - start_t) * 1000,
            )

        runner = SafeShellRunner(workspace_root=ctx.workspace_root, default_timeout_seconds=self.definition.timeout_seconds)
        try:
            exit_code, stdout, stderr = await runner.execute_command(
                command_line=command,
                cwd=cwd,
                env=ctx.env_vars,
            )
            success = exit_code == 0
            return ToolResult(
                call_id=invocation.id,
                success=success,
                data={"exit_code": exit_code, "stdout": stdout, "stderr": stderr},
                error=stderr if not success else None,
                execution_time_ms=(time.time() - start_t) * 1000,
            )
        except Exception as ex:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error=str(ex),
                execution_time_ms=(time.time() - start_t) * 1000,
            )
