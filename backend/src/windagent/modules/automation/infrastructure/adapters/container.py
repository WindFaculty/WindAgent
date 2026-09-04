"""Container runtime adapter (Phase 12).

Stub for Docker/container-isolated execution.  In production this will
launch a short-lived container, mount the workspace as a volume with
read-only/write boundaries, and return the container's output.
"""

from __future__ import annotations

import time

from ...domain.invocation import ToolExecutionContext, ToolInvocation
from ...domain.result import ToolResult


class ContainerAdapter:
    runtime_type = "container"

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start = time.time()
        image = invocation.params.get("image") or "windagent/sandbox:latest"
        command = invocation.params.get("command") or invocation.params.get("cmd") or ""
        return ToolResult(
            call_id=invocation.call_id,
            success=True,
            data={
                "runtime": "container",
                "image": image,
                "command": command,
                "params": invocation.params,
                "note": "container adapter simulation — Docker launch deferred",
            },
            execution_time_ms=(time.time() - start) * 1000,
        )
