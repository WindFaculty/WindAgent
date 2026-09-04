"""Outbox event factory for Agent Runtime (Phase 13)."""

from __future__ import annotations

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.kernel.types import Version


def _eid(value: str) -> EntityId:
    return EntityId(value)


class AgentRuntimeEventFactory:
    """Create canonical ``agent_runtime.*`` envelopes."""

    # -- sessions
    def session_created(self, session_id: str, actor_id: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.session.created",
            aggregate_type="agent_session",
            aggregate_id=_eid(session_id),
            sequence=0,
            payload={"session_id": session_id, "actor_id": actor_id},
            event_version=Version(1),
        )

    def session_transitioned(self, session_id: str, from_state: str, to_state: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.session.transitioned",
            aggregate_type="agent_session",
            aggregate_id=_eid(session_id),
            sequence=0,
            payload={"session_id": session_id, "from_state": from_state, "to_state": to_state},
            event_version=Version(1),
        )

    # -- runs
    def run_created(self, run_id: str, session_id: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.run.created",
            aggregate_type="agent_run",
            aggregate_id=_eid(run_id),
            sequence=0,
            payload={"run_id": run_id, "session_id": session_id},
            event_version=Version(1),
        )

    def run_transitioned(self, run_id: str, from_state: str, to_state: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.run.transitioned",
            aggregate_type="agent_run",
            aggregate_id=_eid(run_id),
            sequence=0,
            payload={"run_id": run_id, "from_state": from_state, "to_state": to_state},
            event_version=Version(1),
        )

    def run_budget_exhausted(self, run_id: str, reason: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.run.budget_exhausted",
            aggregate_type="agent_run",
            aggregate_id=_eid(run_id),
            sequence=0,
            payload={"run_id": run_id, "reason": reason},
            event_version=Version(1),
        )

    # -- tasks
    def task_created(self, task_id: str, session_id: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.task.created",
            aggregate_type="agent_task",
            aggregate_id=_eid(task_id),
            sequence=0,
            payload={"task_id": task_id, "session_id": session_id},
            event_version=Version(1),
        )

    def task_transitioned(self, task_id: str, from_state: str, to_state: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.task.transitioned",
            aggregate_type="agent_task",
            aggregate_id=_eid(task_id),
            sequence=0,
            payload={"task_id": task_id, "from_state": from_state, "to_state": to_state},
            event_version=Version(1),
        )

    def task_completed(self, task_id: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.task.completed",
            aggregate_type="agent_task",
            aggregate_id=_eid(task_id),
            sequence=0,
            payload={"task_id": task_id},
            event_version=Version(1),
        )

    def task_failed(self, task_id: str, error: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.task.failed",
            aggregate_type="agent_task",
            aggregate_id=_eid(task_id),
            sequence=0,
            payload={"task_id": task_id, "error": error},
            event_version=Version(1),
        )

    # -- workflows
    def workflow_created(self, workflow_id: str, session_id: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.workflow.created",
            aggregate_type="agent_workflow",
            aggregate_id=_eid(workflow_id),
            sequence=0,
            payload={"workflow_id": workflow_id, "session_id": session_id},
            event_version=Version(1),
        )

    def workflow_transitioned(self, workflow_id: str, from_state: str, to_state: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.workflow.transitioned",
            aggregate_type="agent_workflow",
            aggregate_id=_eid(workflow_id),
            sequence=0,
            payload={"workflow_id": workflow_id, "from_state": from_state, "to_state": to_state},
            event_version=Version(1),
        )

    # -- checkpoints
    def checkpoint_created(self, checkpoint_id: str, run_id: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.checkpoint.created",
            aggregate_type="agent_checkpoint",
            aggregate_id=_eid(checkpoint_id),
            sequence=0,
            payload={"checkpoint_id": checkpoint_id, "run_id": run_id},
            event_version=Version(1),
        )

    # -- approvals
    def approval_requested(self, approval_id: str, task_id: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.approval.requested",
            aggregate_type="agent_approval",
            aggregate_id=_eid(approval_id),
            sequence=0,
            payload={"approval_id": approval_id, "task_id": task_id},
            event_version=Version(1),
        )

    def approval_resolved(self, approval_id: str, state: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.approval.resolved",
            aggregate_type="agent_approval",
            aggregate_id=_eid(approval_id),
            sequence=0,
            payload={"approval_id": approval_id, "state": state},
            event_version=Version(1),
        )

    # -- delegations
    def delegation_created(self, delegation_id: str, parent_run_id: str, child_run_id: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.delegation.created",
            aggregate_type="agent_delegation",
            aggregate_id=_eid(delegation_id),
            sequence=0,
            payload={"delegation_id": delegation_id, "parent_run_id": parent_run_id, "child_run_id": child_run_id},
            event_version=Version(1),
        )

    def delegation_transitioned(self, delegation_id: str, status: str) -> EventEnvelope:
        return EventEnvelope(
            event_type="agent_runtime.delegation.transitioned",
            aggregate_type="agent_delegation",
            aggregate_id=_eid(delegation_id),
            sequence=0,
            payload={"delegation_id": delegation_id, "status": status},
            event_version=Version(1),
        )
