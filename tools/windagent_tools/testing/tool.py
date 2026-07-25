"""
Canonical Testing Tool for WindAgent Architecture V2 (Phase 19).
Executes pytest test suite and returns normalized test execution results.
"""

from __future__ import annotations
import time
from typing import Any, Dict

from windagent_core.domain.models import ToolInvocation, ToolResult
from windagent_tools.base import BaseTool, ToolDefinition, ToolRiskLevel, ToolExecutionContext
from windagent_tools.shell.runner import SafeShellRunner


class TestRunnerTool(BaseTool):
    __test__ = False  # Prevent pytest from collecting this tool as a test class

    def __init__(self):
        super().__init__(
            ToolDefinition(
                name="run_tests",
                description="Runs automated tests (pytest) and returns structured test results.",
                version="2.0.0",
                risk_level=ToolRiskLevel.PROCESS_EXECUTION,
                capability="testing",
                side_effect_class="process",
                is_idempotent=True,
                is_destructive=False,
                is_reversible=True,
                timeout_seconds=60.0,
                required_permissions=["process_execution"],
                sandbox_requirement="subprocess_sandbox",
                artifact_outputs=["test_results"],
                retry_eligible=True,
                redaction_policy="secrets_only",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "test_path": {"type": "string", "description": "Target test file or directory"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "exit_code": {"type": "integer"},
                        "stdout": {"type": "string"},
                        "passed": {"type": "boolean"},
                    },
                },
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.time()
        test_path = invocation.params.get("test_path", "tests/")
        cmd = f"pytest {test_path} -q"

        runner = SafeShellRunner(workspace_root=ctx.workspace_root, default_timeout_seconds=self.definition.timeout_seconds)
        try:
            exit_code, stdout, stderr = await runner.execute_command(cmd)
            success = exit_code == 0
            return ToolResult(
                call_id=invocation.id,
                success=success,
                data={"exit_code": exit_code, "stdout": stdout, "passed": success},
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
