"""
Canonical Code Search Tool for WindAgent Architecture V2 (Phase 19).
Grep/ripgrep abstraction with bounded output size limits.
"""

from __future__ import annotations
import time
from pathlib import Path
from typing import Any, Dict, List

from windagent_core.contracts.tools import ToolInvocation, ToolResult
from windagent_tools.base import BaseTool, ToolDefinition, ToolRiskLevel, ToolExecutionContext


class CodeSearchTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolDefinition(
                name="code_search",
                description="Performs bounded text/pattern search across workspace code files.",
                version="2.0.0",
                risk_level=ToolRiskLevel.READ_ONLY,
                capability="code_search",
                side_effect_class="none",
                is_idempotent=True,
                is_destructive=False,
                is_reversible=True,
                timeout_seconds=15.0,
                required_permissions=[],
                sandbox_requirement="path_sandbox",
                artifact_outputs=["search_matches"],
                retry_eligible=True,
                redaction_policy="secrets_only",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search string or pattern"},
                        "max_results": {"type": "integer", "default": 50},
                    },
                    "required": ["query"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "total_matches": {"type": "integer"},
                        "matches": {"type": "array"},
                    },
                },
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.time()
        query = invocation.params.get("query", "")
        max_results = min(invocation.params.get("max_results", 50), 100)

        if not query:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error="Parameter 'query' is required.",
                execution_time_ms=(time.time() - start_t) * 1000,
            )

        root = Path(ctx.workspace_root)
        matches: List[Dict[str, Any]] = []

        try:
            for path in root.rglob("*.py"):
                if len(matches) >= max_results:
                    break
                if ".venv" in path.parts or "__pycache__" in path.parts:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    for line_idx, line in enumerate(text.splitlines(), start=1):
                        if query.lower() in line.lower():
                            matches.append({
                                "file": str(path.relative_to(root)),
                                "line_number": line_idx,
                                "content": line.strip(),
                            })
                            if len(matches) >= max_results:
                                break
                except Exception:
                    pass

            return ToolResult(
                call_id=invocation.id,
                success=True,
                data={"query": query, "total_matches": len(matches), "matches": matches},
                execution_time_ms=(time.time() - start_t) * 1000,
            )
        except Exception as ex:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error=str(ex),
                execution_time_ms=(time.time() - start_t) * 1000,
            )
