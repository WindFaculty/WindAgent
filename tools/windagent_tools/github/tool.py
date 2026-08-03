"""
Canonical GitHub Tool for WindAgent Architecture V2 (Phase 19).
API port abstraction for GitHub issues, PRs, and repository metadata.
"""

from __future__ import annotations
import time

from windagent_core.contracts.tools import ToolInvocation, ToolResult
from windagent_tools.base import BaseTool, ToolDefinition, ToolRiskLevel, ToolExecutionContext


class GitHubTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolDefinition(
                name="github_api",
                description="Interacts with GitHub API to query or update issues, PRs, and pull requests.",
                version="2.0.0",
                risk_level=ToolRiskLevel.EXTERNAL_NETWORK,
                capability="github",
                side_effect_class="network",
                is_idempotent=True,
                is_destructive=False,
                is_reversible=True,
                timeout_seconds=20.0,
                required_permissions=["external_network"],
                sandbox_requirement="none",
                artifact_outputs=["github_payload"],
                retry_eligible=True,
                redaction_policy="secrets_only",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["get_issue", "create_issue_comment", "list_prs"]},
                        "repo": {"type": "string"},
                        "issue_number": {"type": "integer"},
                    },
                    "required": ["action", "repo"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "result": {"type": "object"},
                    },
                },
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.time()
        action = invocation.params.get("action", "get_issue")
        repo = invocation.params.get("repo", "")

        if not repo:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error="Parameter 'repo' is required.",
                execution_time_ms=(time.time() - start_t) * 1000,
            )

        return ToolResult(
            call_id=invocation.id,
            success=True,
            data={"action": action, "repo": repo, "status": "simulated_ok"},
            execution_time_ms=(time.time() - start_t) * 1000,
        )
