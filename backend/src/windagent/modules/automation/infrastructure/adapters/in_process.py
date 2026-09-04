"""In-process runtime adapter (Phase 12).

Handles filesystem, general, and any tool whose implementation is a
registered async callable living in the same process.  Built-ins like
``read_file`` and ``write_file`` are registered here so offline tests do
not require subprocess or network.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from ...domain.invocation import ToolExecutionContext, ToolInvocation
from ...domain.result import ToolResult
from ...domain.sandbox import resolve_safe_path

ToolCallable = Callable[[ToolInvocation, ToolExecutionContext], Awaitable[ToolResult]]


class InProcessAdapter:
    """Executes tool callables registered in-process."""

    runtime_type = "in_process"

    def __init__(self) -> None:
        self._handlers: dict[str, ToolCallable] = {}
        self._register_builtins()

    def register(self, name: str, handler: ToolCallable) -> None:
        self._handlers[name] = handler

    def _register_builtins(self) -> None:
        self._handlers["read_file"] = self._handle_read_file
        self._handlers["write_file"] = self._handle_write_file
        self._handlers["echo"] = self._handle_echo

    async def _handle_read_file(self, inv: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start = time.time()
        file_path = inv.params.get("file_path") or inv.params.get("path")
        if not file_path:
            return ToolResult(call_id=inv.call_id, success=False, error="file_path is required.", execution_time_ms=(time.time() - start) * 1000)
        try:
            safe = resolve_safe_path(str(file_path), ctx.workspace_root)
            if not safe.exists() or not safe.is_file():
                return ToolResult(call_id=inv.call_id, success=False, error=f"File not found: {file_path}", execution_time_ms=(time.time() - start) * 1000)
            if safe.stat().st_size > 5 * 1024 * 1024:
                return ToolResult(call_id=inv.call_id, success=False, error="File too large (>5MB)", execution_time_ms=(time.time() - start) * 1000)
            content = safe.read_text(encoding="utf-8", errors="replace")
            return ToolResult(
                call_id=inv.call_id,
                success=True,
                data={"file_path": str(safe), "content": content, "bytes": len(content.encode("utf-8"))},
                execution_time_ms=(time.time() - start) * 1000,
            )
        except Exception as ex:
            return ToolResult(call_id=inv.call_id, success=False, error=str(ex), execution_time_ms=(time.time() - start) * 1000)

    async def _handle_write_file(self, inv: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start = time.time()
        file_path = inv.params.get("file_path") or inv.params.get("path")
        content = inv.params.get("content", "")
        if not file_path:
            return ToolResult(call_id=inv.call_id, success=False, error="file_path is required.", execution_time_ms=(time.time() - start) * 1000)
        try:
            safe = resolve_safe_path(str(file_path), ctx.workspace_root)
            safe.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write
            import tempfile

            parent_dir = str(safe.parent)
            with tempfile.NamedTemporaryFile("w", dir=parent_dir, delete=False, encoding="utf-8") as tmp:
                tmp.write(str(content))
                tmp_name = tmp.name
            Path(tmp_name).replace(safe)
            return ToolResult(
                call_id=inv.call_id,
                success=True,
                data={"file_path": str(safe), "bytes_written": len(str(content).encode("utf-8"))},
                execution_time_ms=(time.time() - start) * 1000,
            )
        except Exception as ex:
            return ToolResult(call_id=inv.call_id, success=False, error=str(ex), execution_time_ms=(time.time() - start) * 1000)

    async def _handle_echo(self, inv: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start = time.time()
        return ToolResult(call_id=inv.call_id, success=True, data={"echo": inv.params}, execution_time_ms=(time.time() - start) * 1000)

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        handler = self._handlers.get(invocation.tool_name)
        if handler is None:
            return ToolResult(
                call_id=invocation.call_id,
                success=True,
                data={"tool": invocation.tool_name, "params": invocation.params, "runtime": "in_process", "note": "no in-process handler; treated as no-op success for parity"},
            )
        return await handler(invocation, ctx)
