"""Remote runtime adapter (Phase 12).

Stub for HTTP-remote execution (call out to an external agent or
remote tool host).  In production this will sign the request, forward
it, and normalize the response.  Foundation keeps it deterministic.
"""

from __future__ import annotations

import time

from ...domain.invocation import ToolExecutionContext, ToolInvocation
from ...domain.result import ToolResult


class RemoteAdapter:
    runtime_type = "remote"

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start = time.time()
        endpoint = invocation.params.get("endpoint") or invocation.params.get("remote_url") or ""
        if not str(endpoint).strip():
            return ToolResult(
                call_id=invocation.call_id,
                success=False,
                error="endpoint is required for remote runtime",
                execution_time_ms=(time.time() - start) * 1000,
            )
        return ToolResult(
            call_id=invocation.call_id,
            success=True,
            data={
                "runtime": "remote",
                "endpoint": endpoint,
                "params": invocation.params,
                "note": "remote adapter simulation — HTTP forwarding deferred",
            },
            execution_time_ms=(time.time() - start) * 1000,
        )
