"""Automation event factory (Phase 12).

Seven ``automation.*`` envelopes recorded atomically with the domain write
via the transactional outbox (plan section 10 pattern).
"""

from __future__ import annotations

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.kernel.types import Version


def _eid(value: str) -> EntityId:
    return EntityId(value)


class AutomationEventFactory:
    """Create canonical ``automation.*`` envelopes."""

    def tool_registered(self, tool_id: str, name: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="automation.tool.registered",
            aggregate_type="automation_tool",
            aggregate_id=_eid(tool_id),
            sequence=0,
            payload={"tool_id": tool_id, "name": name},
            event_version=Version(1),
        )

    def tool_updated(self, tool_id: str, name: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="automation.tool.updated",
            aggregate_type="automation_tool",
            aggregate_id=_eid(tool_id),
            sequence=1,
            payload={"tool_id": tool_id, "name": name},
            event_version=Version(1),
        )

    def tool_deregistered(self, tool_id: str, name: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="automation.tool.deregistered",
            aggregate_type="automation_tool",
            aggregate_id=_eid(tool_id),
            sequence=2,
            payload={"tool_id": tool_id, "name": name},
            event_version=Version(1),
        )

    def tool_invoked(self, run_id: str, tool_name: str, invocation_id: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="automation.tool.invoked",
            aggregate_type="automation_tool_run",
            aggregate_id=_eid(run_id),
            sequence=0,
            payload={"run_id": run_id, "tool_name": tool_name, "invocation_id": invocation_id},
            event_version=Version(1),
        )

    def tool_succeeded(self, run_id: str, tool_name: str, execution_time_ms: int) -> EventEnvelope:
        return EventEnvelope(
            event_type="automation.tool.succeeded",
            aggregate_type="automation_tool_run",
            aggregate_id=_eid(run_id),
            sequence=1,
            payload={"run_id": run_id, "tool_name": tool_name, "execution_time_ms": execution_time_ms},
            event_version=Version(1),
        )

    def tool_failed(self, run_id: str, tool_name: str, error: str | None) -> EventEnvelope:
        return EventEnvelope(
            event_type="automation.tool.failed",
            aggregate_type="automation_tool_run",
            aggregate_id=_eid(run_id),
            sequence=2,
            payload={"run_id": run_id, "tool_name": tool_name, "error": error or ""},
            event_version=Version(1),
        )

    def tool_denied(self, run_id: str, tool_name: str, reason: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="automation.tool.denied",
            aggregate_type="automation_tool_run",
            aggregate_id=_eid(run_id),
            sequence=3,
            payload={"run_id": run_id, "tool_name": tool_name, "reason": reason},
            event_version=Version(1),
        )
