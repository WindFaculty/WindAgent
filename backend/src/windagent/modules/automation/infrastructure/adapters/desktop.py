"""Desktop runtime adapter (Phase 12).

Stub for Tauri/desktop IPC capabilities (screen capture, native dialogs,
file pickers).  Keeps the contract ready for Phase: Desktop without
pulling native code into the foundation.
"""

from __future__ import annotations

import time

from ...domain.invocation import ToolExecutionContext, ToolInvocation
from ...domain.result import ToolResult


class DesktopAdapter:
    runtime_type = "desktop"

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start = time.time()
        capability = invocation.params.get("capability") or invocation.tool_name
        return ToolResult(
            call_id=invocation.call_id,
            success=True,
            data={
                "runtime": "desktop",
                "capability": capability,
                "params": invocation.params,
                "note": "desktop adapter simulation — IPC bridge wiring deferred to Desktop milestone",
            },
            execution_time_ms=(time.time() - start) * 1000,
        )
