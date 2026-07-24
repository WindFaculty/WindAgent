# WindAgent Core Contracts & Interfaces Specification

## 1. Overview

`windagent_core/contracts/` defines pure Python `Protocol` definitions for all cross-package boundaries.
Infrastructure packages (`windagent_storage`, `windagent_providers`, `windagent_execution`) implement these contracts.

---

## 2. Core Protocol Definitions

### 2.1 Repository & UnitOfWork Contracts

```python
from typing import Protocol, Optional
from windagent_core.domain.models import Task, TaskRun, Session, WorkflowDefinition, WorkflowRun
from windagent_core.domain.types import TaskId, TaskRunId, SessionId, WorkflowId, WorkflowRunId

class TaskRepository(Protocol):
    async def get_by_id(self, task_id: TaskId) -> Optional[Task]: ...
    async def save(self, task: Task) -> None: ...

class TaskRunRepository(Protocol):
    async def get_by_id(self, run_id: TaskRunId) -> Optional[TaskRun]: ...
    async def save(self, task_run: TaskRun) -> None: ...

class WorkflowRepository(Protocol):
    async def get_by_id(self, workflow_id: WorkflowId) -> Optional[WorkflowDefinition]: ...
    async def save(self, workflow: WorkflowDefinition) -> None: ...

class WorkflowRunRepository(Protocol):
    async def get_by_id(self, run_id: WorkflowRunId) -> Optional[WorkflowRun]: ...
    async def save(self, workflow_run: WorkflowRun) -> None: ...

class EventStore(Protocol):
    async def append(self, event: EventEnvelope) -> None: ...

class OutboxWriter(Protocol):
    async def write(self, event: EventEnvelope) -> None: ...

class UnitOfWork(Protocol):
    tasks: TaskRepository
    task_runs: TaskRunRepository
    workflows: WorkflowRepository
    workflow_runs: WorkflowRunRepository
    events: EventStore
    outbox: OutboxWriter

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
```

---

### 2.2 Execution Runtime & Model Gateway Contracts

```python
class ExecutionRuntimePort(Protocol):
    async def dispatch(self, step_run_id: StepRunId, payload: dict) -> None: ...
    async def cancel(self, step_run_id: StepRunId) -> None: ...

class ModelGatewayPort(Protocol):
    async def execute(self, request: ModelRequest) -> ModelResponse: ...
```

---

### 2.3 Security & SecretStore Contracts

```python
class PermissionEvaluator(Protocol):
    async def evaluate(self, request: PermissionEvaluationRequest) -> PermissionDecision: ...

class SecretStore(Protocol):
    async def resolve(self, ref: SecretRef) -> SecretValue: ...
    async def store(self, name: SecretName, value: SecretValue) -> SecretRef: ...
    async def delete(self, ref: SecretRef) -> None: ...
```
