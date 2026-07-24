# WindAgent Core Lifecycle Specification

## 1. Overview

State machine ownership for all core aggregates (Task, Workflow, Step, Session) resides exclusively in `windagent_core/domain/lifecycle.py`.
Orchestration and backend services must delegate state transitions to core transition functions.

---

## 2. Canonical State Machine Enumerations

### 2.1 TaskState (15 States)
```python
from enum import Enum

class TaskState(str, Enum):
    RECEIVED = "RECEIVED"
    CLASSIFYING = "CLASSIFYING"
    CONTEXT_BUILDING = "CONTEXT_BUILDING"
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_PERMISSION = "WAITING_PERMISSION"
    PAUSED = "PAUSED"
    RETRY_WAIT = "RETRY_WAIT"
    RECOVERING = "RECOVERING"
    VERIFYING = "VERIFYING"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
```
* **Terminal States**: `COMPLETED`, `FAILED`, `CANCELLED`.

### 2.2 WorkflowState
```python
class WorkflowState(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
```
* **Terminal States**: `COMPLETED`, `FAILED`, `CANCELLED`.

### 2.3 StepState
```python
class StepState(str, Enum):
    BLOCKED = "BLOCKED"
    READY = "READY"
    CLAIMED = "CLAIMED"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    WAITING_PERMISSION = "WAITING_PERMISSION"
    RETRY_WAIT = "RETRY_WAIT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"
```
* **Terminal States**: `COMPLETED`, `FAILED`, `SKIPPED`, `CANCELLED`.

### 2.4 SessionState
```python
class SessionState(str, Enum):
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"
```
* **Terminal States**: `COMPLETED`, `FAILED`, `CANCELLED`, `ARCHIVED`.

---

## 3. Legal State Transition Matrix

Core exposes typed transition logic:

```python
class TaskLifecycle:
    LEGAL_TRANSITIONS = {
        TaskState.RECEIVED: {TaskState.CLASSIFYING, TaskState.CANCELLED},
        TaskState.CLASSIFYING: {TaskState.CONTEXT_BUILDING, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.CONTEXT_BUILDING: {TaskState.PLANNING, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.PLANNING: {TaskState.READY, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.READY: {TaskState.RUNNING, TaskState.PAUSED, TaskState.CANCELLED},
        TaskState.RUNNING: {
            TaskState.WAITING_PERMISSION, TaskState.PAUSED, TaskState.RETRY_WAIT,
            TaskState.RECOVERING, TaskState.VERIFYING, TaskState.REVIEWING,
            TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED
        },
        TaskState.WAITING_PERMISSION: {TaskState.RUNNING, TaskState.PAUSED, TaskState.CANCELLED, TaskState.FAILED},
        TaskState.PAUSED: {TaskState.RUNNING, TaskState.CANCELLED},
        TaskState.RETRY_WAIT: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED},
        TaskState.RECOVERING: {TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.VERIFYING: {TaskState.REVIEWING, TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.REVIEWING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.COMPLETED: set(),
        TaskState.FAILED: set(),
        TaskState.CANCELLED: set(),
    }

    @classmethod
    def transition(cls, current: TaskState, target: TaskState) -> TaskState:
        if current in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}:
            raise TerminalStateMutationError(f"Cannot mutate terminal task state {current}")
        if target not in cls.LEGAL_TRANSITIONS.get(current, set()):
            raise InvalidStateTransitionError(f"Illegal transition from {current} to {target}")
        return target
```

---

## 4. Optimistic Concurrency Invariants

All persistence transitions must supply `expected_version`:

```python
class StateTransitionResult(BaseModel):
    aggregate_id: str
    from_state: str
    to_state: str
    previous_version: int
    new_version: int
    occurred_at: datetime
```

If `expected_version` does not match durable state, `ConcurrencyConflictError` is raised.
