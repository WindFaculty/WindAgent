"""Durable job handlers for Automation (Phase 12)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from windagent.kernel.types.json import JSONValue

from ..application.runtime import AutomationServices


class AutomationToolExecuteJobHandler:
    """Handles ``automation.tool.execute`` — durable, fencing-protected."""

    job_type = "automation.tool.execute"

    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: Mapping[str, JSONValue]) -> Any:
        from ..application.runtime import container_for, resolve_services
        from ..domain.errors import (
            AutomationPolicyApprovalRequiredError,
            AutomationPolicyDeniedError,
        )

        services = resolve_services(self._services)
        container = container_for(services)
        tool_name = str(payload.get("tool_name") or payload.get("name") or "")
        if not tool_name.strip():
            raise ValueError("payload.tool_name is required")
        params = dict(payload.get("params") or payload.get("parameters") or {})  # type: ignore[arg-type]
        workspace_root = str(payload.get("workspace_root") or "/tmp")
        invocation_id = str(payload.get("invocation_id") or payload.get("call_id") or "") or None
        actor_id = payload.get("actor_id")
        correlation_id = payload.get("correlation_id")
        causation_id = payload.get("causation_id")
        trace_id = payload.get("trace_id")
        user_approved = bool(payload.get("user_approved", False))

        try:
            view = await container.automation.execute_tool(
                tool_name=tool_name,
                params=params,
                workspace_root=workspace_root,
                actor_id=str(actor_id) if actor_id else None,
                correlation_id=str(correlation_id) if correlation_id else None,
                causation_id=str(causation_id) if causation_id else None,
                trace_id=str(trace_id) if trace_id else None,
                user_approved=user_approved,
                invocation_id=invocation_id,
            )
            return {"run_id": view.run_id, "status": view.status, "result": view.result, "error": view.error}
        except (AutomationPolicyDeniedError, AutomationPolicyApprovalRequiredError) as ex:
            # Policy denials are not retryable — return payload so worker marks job succeeded
            # with a denial outcome instead of retrying indefinitely.
            return {"status": "denied", "error": str(ex), "tool_name": tool_name, "policy": str(ex.context) if getattr(ex, "context", None) else None}
