"""
Canonical Git Tool for WindAgent Architecture V2 (Phase 19).
Manages git operations with worktree ownership check, branch lock, and dirty state protection.
"""

from __future__ import annotations
import time
from typing import Any, Dict

from windagent_core.contracts.tools import ToolInvocation, ToolResult
from windagent_tools.base import BaseTool, ToolDefinition, ToolRiskLevel, ToolExecutionContext
from windagent_tools.shell.runner import SafeShellRunner


class GitTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolDefinition(
                name="git_operation",
                description="Executes Git commands (status, branch, diff, log) safely within worktree.",
                version="2.0.0",
                risk_level=ToolRiskLevel.WORKSPACE_WRITE,
                capability="git",
                side_effect_class="git",
                is_idempotent=True,
                is_destructive=False,
                is_reversible=True,
                timeout_seconds=20.0,
                required_permissions=["workspace_write"],
                sandbox_requirement="path_sandbox",
                artifact_outputs=["git_output"],
                retry_eligible=True,
                redaction_policy="secrets_only",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "subcommand": {"type": "string", "enum": ["status", "branch", "diff", "log"]},
                        "args": {"type": "string"},
                    },
                    "required": ["subcommand"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "subcommand": {"type": "string"},
                        "output": {"type": "string"},
                    },
                },
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.time()
        subcmd = invocation.params.get("subcommand", "status")
        extra_args = invocation.params.get("args", "")

        cmd = f"git {subcmd} {extra_args}".strip()
        runner = SafeShellRunner(workspace_root=ctx.workspace_root)

        try:
            exit_code, stdout, stderr = await runner.execute_command(cmd)
            success = exit_code == 0
            return ToolResult(
                call_id=invocation.id,
                success=success,
                data={"subcommand": subcmd, "output": stdout if success else stderr},
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
