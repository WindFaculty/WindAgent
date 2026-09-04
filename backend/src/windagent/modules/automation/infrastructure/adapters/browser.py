"""Browser runtime adapter (Phase 12).

Stub that would delegate to a Playwright/Browser runtime in production.
For the foundation it validates policy-gated semantics and returns a
deterministic simulated result so E2E tests stay offline.

The real production hardening (Windows Graphics Capture, session lifecycle,
state encryption) will be wired through this adapter when Desktop/Browser
caps are introduced — the contract stays the same.
"""

from __future__ import annotations

import time

from ...domain.invocation import ToolExecutionContext, ToolInvocation
from ...domain.result import ToolResult

ALLOW_BROWSER_CONSENT_FLAG = "browser_consent"


class BrowserAdapter:
    """Deterministic browser adapter (offline simulation)."""

    runtime_type = "browser"

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        start = time.time()
        # Browser actions require explicit consent flag in params OR user_approved
        params = invocation.params
        needs_consent = True
        if ctx.user_approved or params.get(ALLOW_BROWSER_CONSENT_FLAG) is True:
            needs_consent = False
        # For foundation we still allow execution but surface consent metadata
        action = params.get("action") or invocation.tool_name
        url = params.get("url") or params.get("target_url") or ""
        return ToolResult(
            call_id=invocation.call_id,
            success=True,
            data={
                "runtime": "browser",
                "action": action,
                "url": url,
                "consent_verified": not needs_consent,
                "session_id": ctx.session_id,
                "note": "browser adapter simulation — real Playwright wiring deferred to browser hardening phase",
            },
            execution_time_ms=(time.time() - start) * 1000,
        )
