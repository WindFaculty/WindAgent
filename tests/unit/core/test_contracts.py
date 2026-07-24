"""
Unit tests for WindAgent Core Contracts & Protocol Conformance (Phase 4).
Verifies runtime checkability and structure of UnitOfWork, ExecutionRuntimePort,
ModelGatewayPort, PermissionEvaluator, SecretStore, and Repositories protocols.
"""

import pytest
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from windagent_core.contracts import (
    Clock, IdGenerator, TaskRepository, TaskRunRepository, SessionRepository,
    WorkflowRepository, WorkflowRunRepository, EventStore, OutboxWriter, EventPublisher,
    ArtifactRepository, UnitOfWork, ExecutionRuntimePort, ModelGatewayPort, SecretStore,
    PermissionEvaluator, AuditSink
)
from windagent_core.domain.types import TaskId, TaskRunId, SessionId, StepRunId, ArtifactId
from windagent_core.domain.models import Task, TaskRun, Session, ModelRequest, ModelResponse, ArtifactRef
from windagent_core.events.envelope import EventEnvelope
from windagent_core.security.types import (
    PermissionEvaluationRequest, PermissionDecision, SecretRef, SecretName, SecretValue, RedactedValue, RiskLevel, Principal
)


# Dummy implementations to test protocol conformance

class DummyTaskRepo:
    async def get_by_id(self, task_id: TaskId) -> Optional[Task]:
        return None
    async def save(self, task: Task) -> None:
        pass
    async def list_by_session(self, session_id: SessionId) -> List[Task]:
        return []


class DummyTaskRunRepo:
    async def get_by_id(self, run_id: TaskRunId) -> Optional[TaskRun]:
        return None
    async def save(self, task_run: TaskRun) -> None:
        pass


class DummyEventStore:
    async def append(self, event: EventEnvelope) -> None:
        pass
    async def get_events(self, stream_id: str, after_sequence: int = 0, limit: int = 100) -> List[EventEnvelope]:
        return []


class DummyOutboxWriter:
    async def write(self, event: EventEnvelope) -> None:
        pass


class DummyUoW:
    def __init__(self):
        self.tasks = DummyTaskRepo()
        self.task_runs = DummyTaskRunRepo()
        self.workflows = None
        self.workflow_runs = None
        self.events = DummyEventStore()
        self.outbox = DummyOutboxWriter()

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> "DummyUoW":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class DummyExecutionRuntimeAdapter:
    async def dispatch(self, step_run_id: StepRunId, payload: Dict[str, Any]) -> None:
        pass
    async def cancel(self, step_run_id: StepRunId) -> None:
        pass
    async def heartbeat(self, step_run_id: StepRunId) -> None:
        pass


class DummyModelGateway:
    async def execute(self, request: ModelRequest) -> ModelResponse:
        pass


class DummySecretStore:
    async def resolve(self, ref: SecretRef) -> SecretValue:
        return RedactedValue("secret")
    async def store(self, name: SecretName, value: SecretValue) -> SecretRef:
        return SecretRef.create(name, value.get_secret_value())
    async def delete(self, ref: SecretRef) -> None:
        pass


class DummyPermissionEvaluator:
    async def evaluate(self, request: PermissionEvaluationRequest) -> PermissionDecision:
        return PermissionDecision(
            outcome="ALLOW",
            risk_level=RiskLevel.LOW,
            reason_code="DEFAULT_ALLOW",
            human_reason="Action allowed by default test policy"
        )


def test_protocol_runtime_checkability():
    task_repo = DummyTaskRepo()
    assert isinstance(task_repo, TaskRepository)

    task_run_repo = DummyTaskRunRepo()
    assert isinstance(task_run_repo, TaskRunRepository)

    event_store = DummyEventStore()
    assert isinstance(event_store, EventStore)

    outbox = DummyOutboxWriter()
    assert isinstance(outbox, OutboxWriter)

    uow = DummyUoW()
    assert isinstance(uow, UnitOfWork)

    exec_adapter = DummyExecutionRuntimeAdapter()
    assert isinstance(exec_adapter, ExecutionRuntimePort)

    gateway = DummyModelGateway()
    assert isinstance(gateway, ModelGatewayPort)

    secret_store = DummySecretStore()
    assert isinstance(secret_store, SecretStore)

    evaluator = DummyPermissionEvaluator()
    assert isinstance(evaluator, PermissionEvaluator)


@pytest.mark.asyncio
async def test_permission_evaluator_decision_structure():
    evaluator = DummyPermissionEvaluator()
    req = PermissionEvaluationRequest(
        principal=Principal(id="user_1"),
        action="file:read",
        target="/tmp/test.txt"
    )
    decision = await evaluator.evaluate(req)
    assert isinstance(decision, PermissionDecision)
    assert decision.is_allowed
    assert decision.outcome == "ALLOW"
