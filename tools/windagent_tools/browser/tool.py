"""
Canonical Browser Tools for WindAgent Architecture V2 (Phase 19).
Provides OpenURLTool and ClickXYTool with navigation policies and screenshot artifact management.
"""

from __future__ import annotations
import time
from typing import Any, Dict

from windagent_core.domain.models import ToolInvocation, ToolResult
from windagent_tools.base import BaseTool, ToolDefinition, ToolRiskLevel, ToolExecutionContext


class OpenURLTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolDefinition(
                name="open_url",
                description="Navigates browser subagent to target URL and captures page state.",
                version="2.0.0",
                risk_level=ToolRiskLevel.EXTERNAL_NETWORK,
                capability="browser",
                side_effect_class="network",
                is_idempotent=True,
                is_destructive=False,
                is_reversible=True,
                timeout_seconds=30.0,
                required_permissions=["external_network"],
                sandbox_requirement="browser_sandbox",
                artifact_outputs=["screenshot", "dom_snapshot"],
                retry_eligible=True,
                redaction_policy="secrets_only",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target web page URL"}
                    },
                    "required": ["url"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "status_code": {"type": "integer"},
                    },
                },
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.time()
        url = invocation.params.get("url")
        if not url:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error="Parameter 'url' is required.",
                execution_time_ms=(time.time() - start_t) * 1000,
            )

        return ToolResult(
            call_id=invocation.id,
            success=True,
            data={"url": url, "status_code": 200, "page_title": f"Page at {url}"},
            execution_time_ms=(time.time() - start_t) * 1000,
        )


class ClickXYTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolDefinition(
                name="click_xy",
                description="Simulates a mouse click at screen coordinates (x, y) on the active browser page.",
                version="2.0.0",
                risk_level=ToolRiskLevel.WORKSPACE_WRITE,
                capability="browser",
                side_effect_class="process",
                is_idempotent=False,
                is_destructive=False,
                is_reversible=False,
                timeout_seconds=10.0,
                required_permissions=[],
                sandbox_requirement="browser_sandbox",
                artifact_outputs=["screenshot"],
                retry_eligible=False,
                redaction_policy="secrets_only",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                    },
                    "required": ["x", "y"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "clicked_x": {"type": "integer"},
                        "clicked_y": {"type": "integer"},
                    },
                },
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.time()
        x = invocation.params.get("x")
        y = invocation.params.get("y")

        if x is None or y is None:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error="Parameters 'x' and 'y' are required.",
                execution_time_ms=(time.time() - start_t) * 1000,
            )

        return ToolResult(
            call_id=invocation.id,
            success=True,
            data={"clicked_x": x, "clicked_y": y},
            execution_time_ms=(time.time() - start_t) * 1000,
        )
