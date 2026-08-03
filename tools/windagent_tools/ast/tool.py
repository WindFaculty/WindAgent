"""
Canonical AST Tool for WindAgent Architecture V2 (Phase 19).
Extracts Python classes, functions, and imports via ast parsing.
"""

from __future__ import annotations
import ast
import time

from windagent_core.contracts.tools import ToolInvocation, ToolResult
from windagent_tools.base import BaseTool, ToolDefinition, ToolRiskLevel, ToolExecutionContext
from windagent_tools.filesystem.sandbox import PathSandbox


class ASTSymbolExtractorTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolDefinition(
                name="ast_extract_symbols",
                description="Parses Python source file and extracts classes, functions, and top-level docstrings.",
                version="2.0.0",
                risk_level=ToolRiskLevel.READ_ONLY,
                capability="ast",
                side_effect_class="none",
                is_idempotent=True,
                is_destructive=False,
                is_reversible=True,
                timeout_seconds=10.0,
                required_permissions=[],
                sandbox_requirement="path_sandbox",
                artifact_outputs=["symbol_tree"],
                retry_eligible=True,
                redaction_policy="none",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Target Python file path"}
                    },
                    "required": ["file_path"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "classes": {"type": "array"},
                        "functions": {"type": "array"},
                    },
                },
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.time()
        file_path_str = invocation.params.get("file_path")
        if not file_path_str:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error="Parameter 'file_path' is required.",
                execution_time_ms=(time.time() - start_t) * 1000,
            )

        try:
            sandbox = PathSandbox(ctx.workspace_root)
            safe_path = sandbox.resolve_safe_path(file_path_str)
            code = safe_path.read_text(encoding="utf-8")

            tree = ast.parse(code)
            classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]

            return ToolResult(
                call_id=invocation.id,
                success=True,
                data={"classes": classes, "functions": functions, "total_symbols": len(classes) + len(functions)},
                execution_time_ms=(time.time() - start_t) * 1000,
            )
        except Exception as ex:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error=str(ex),
                execution_time_ms=(time.time() - start_t) * 1000,
            )
