# WindAgent Core Event Model Specification

## 1. Dotted Event Naming Taxonomy

All system events follow a unified **dotted taxonomy** (`<domain_aggregate>.<action/state>`).
Redundant prefixes like `orchestration.task.created` or `TaskCreatedDomainEvent` are eliminated.

### 1.1 Canonical Event Names
* **Task Events**: `task.created`, `task.transitioned`, `task.completed`, `task.failed`, `task.cancelled`
* **Workflow Events**: `workflow.created`, `workflow.started`, `workflow.completed`, `workflow.failed`
* **Step Events**: `step.ready`, `step.claimed`, `step.dispatched`, `step.started`, `step.completed`, `step.failed`
* **Execution Events**: `execution.heartbeat`, `execution.lost`
* **Permission Events**: `permission.requested`, `permission.granted`, `permission.denied`
* **Provider Events**: `provider.request.started`, `provider.response.delta`, `provider.response.completed`, `provider.request.failed`
* **Artifact Events**: `artifact.created`
* **System Events**: `system.error`

---

## 2. Canonical Event Envelope

All events emitted within WindAgent must conform to core's `EventEnvelope`:

```python
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field
from windagent_core.domain.types import EventId, SessionId

class EventEnvelope(BaseModel):
    event_id: EventId
    event_type: str
    schema_version: int = 1
    stream_id: str
    aggregate_id: Optional[str] = None
    aggregate_type: Optional[str] = None
    sequence: int
    occurred_at: datetime
    recorded_at: Optional[datetime] = None
    session_id: Optional[SessionId] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[EventId] = None
    trace_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True, extra="forbid")
```

---

## 3. Sequence & Outbox Semantics

1. **Durable Sequence Counter**: Sequence numbers are issued monotonically per stream by `EventStore` in `windagent_storage`.
2. **Unique Constraints**: `UNIQUE(stream_id, sequence)` and `UNIQUE(event_id)`.
3. **Transactional Outbox**: Events are written atomically with aggregate state changes in the same database transaction.
4. **No Uncommitted Broadcasts**: Event producers emit to in-memory buses or WebSockets ONLY after successful database transaction commit.

---

## 4. Boundary Compatibility Mappers

Legacy event names (e.g. `task_created`, `TASK_STATE_CHANGED`) are translated **strictly at the API/WebSocket edge**:
* `apps/api/windagent_api/adapters/legacy_event_mapper.py`
* `apps/backend/compatibility/websocket_mapper.py`

`windagent_core` contains NO legacy conversion logic.
