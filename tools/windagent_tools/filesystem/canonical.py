"""
Canonical Filesystem Tools for WindAgent Architecture V2 (Phase 19).
Provides ReadFileTool and WriteFileTool with path sandbox validation, atomic write, and symlink protection.
"""

from __future__ import annotations
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

from windagent_core.contracts.tools import ToolInvocation, ToolResult
from windagent_tools.base import BaseTool, ToolDefinition, ToolRiskLevel, ToolExecutionContext
from windagent_tools.filesystem.sandbox import PathSandbox


class ReadFileTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolDefinition(
                name="read_file",
                description="Reads text content from a file safely within workspace sandbox.",
                version="2.0.0",
                risk_level=ToolRiskLevel.READ_ONLY,
                capability="filesystem",
                side_effect_class="none",
                is_idempotent=True,
                is_destructive=False,
                is_reversible=True,
                timeout_seconds=10.0,
                required_permissions=[],
                sandbox_requirement="path_sandbox",
                artifact_outputs=["file_content"],
                retry_eligible=True,
                redaction_policy="secrets_only",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Relative or absolute path within workspace"}
                    },
                    "required": ["file_path"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "content": {"type": "string"},
                        "bytes": {"type": "integer"},
                    },
                },
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.time()
        file_path_str = invocation.params.get("file_path") or invocation.params.get("path")
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
            sandbox.check_file_size(safe_path)

            if not safe_path.exists() or not safe_path.is_file():
                return ToolResult(
                    call_id=invocation.id,
                    success=False,
                    error=f"File not found: '{file_path_str}'",
                    execution_time_ms=(time.time() - start_t) * 1000,
                )

            content = safe_path.read_text(encoding="utf-8", errors="replace")
            return ToolResult(
                call_id=invocation.id,
                success=True,
                data={"file_path": str(safe_path), "content": content, "bytes": len(content.encode("utf-8"))},
                execution_time_ms=(time.time() - start_t) * 1000,
            )
        except Exception as ex:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error=str(ex),
                execution_time_ms=(time.time() - start_t) * 1000,
            )


class WriteFileTool(BaseTool):
    def __init__(self):
        super().__init__(
            ToolDefinition(
                name="write_file",
                description="Writes text content atomically to a file within workspace sandbox.",
                version="2.0.0",
                risk_level=ToolRiskLevel.WORKSPACE_WRITE,
                capability="filesystem",
                side_effect_class="filesystem",
                is_idempotent=True,
                is_destructive=False,
                is_reversible=True,
                timeout_seconds=15.0,
                required_permissions=["workspace_write"],
                sandbox_requirement="path_sandbox",
                artifact_outputs=["written_file"],
                retry_eligible=True,
                redaction_policy="secrets_only",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Target file path"},
                        "content": {"type": "string", "description": "Text content to write"},
                    },
                    "required": ["file_path", "content"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "bytes_written": {"type": "integer"},
                    },
                },
            )
        )

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start_t = time.time()
        file_path_str = invocation.params.get("file_path") or invocation.params.get("path")
        content = invocation.params.get("content", "")

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

            # Create parent directory if missing
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write via temporary file
            parent_dir = str(safe_path.parent)
            with tempfile.NamedTemporaryFile("w", dir=parent_dir, delete=False, encoding="utf-8") as tmp:
                tmp.write(content)
                tmp_name = tmp.name

            os.replace(tmp_name, safe_path)

            return ToolResult(
                call_id=invocation.id,
                success=True,
                data={"file_path": str(safe_path), "path": str(safe_path), "bytes_written": len(content.encode("utf-8")), "bytes": len(content.encode("utf-8"))},
                execution_time_ms=(time.time() - start_t) * 1000,
            )
        except Exception as ex:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error=str(ex),
                execution_time_ms=(time.time() - start_t) * 1000,
            )
