# WindAgent Core Canonical Model Specification

## 1. Overview & Architectural Directives

`windagent_core` is the **Shared Kernel** for the entire WindAgent workspace.
It defines all canonical domain entities, value objects, typed IDs, and shared contracts that cross package boundaries.

### Architectural Rules
1. **Pydantic v2 Base**: All domain models are declared using Pydantic v2 `BaseModel` or `RootModel`.
2. **Immutable Domain Invariants**: Core models validate data at instantiation time (`validate_assignment=True`, `extra="forbid"` where appropriate).
3. **No Infrastructure Dependencies**: Core depends ONLY on `pydantic>=2.7` and `typing-extensions`. It NEVER imports FastAPI, SQLAlchemy, httpx, cryptography, or any other package within `apps/*` or `windagent_*`.

---

## 2. Typed IDs System

Domain IDs are split into two distinct type hierarchies: **UUID Domain IDs** and **Opaque External/Runtime IDs**.

### 2.1 UUID Domain IDs
UUID domain entities use strong typing around UUIDv4 to guarantee global uniqueness and valid formatting.

```python
from uuid import UUID
from pydantic import RootModel

class UUIDEntityId(RootModel[UUID]):
    """Base class for all internal UUID-backed domain entity identifiers."""
    pass

class TaskId(UUIDEntityId): pass
class TaskRunId(UUIDEntityId): pass
class SessionId(UUIDEntityId): pass
class WorkflowId(UUIDEntityId): pass
class WorkflowRunId(UUIDEntityId): pass
class StepId(UUIDEntityId): pass
class StepRunId(UUIDEntityId): pass
class EventId(UUIDEntityId): pass
class ArtifactId(UUIDEntityId): pass
class PermissionRequestId(UUIDEntityId): pass
class ToolCallId(UUIDEntityId): pass
class ModelCallId(UUIDEntityId): pass
```

### 2.2 Opaque External/Runtime IDs
External, provider, or worker-assigned IDs use string-backed opaque typed wrappers.

```python
class OpaqueId(RootModel[str]):
    """Base class for external or runtime opaque identifiers."""
    pass

class ProviderId(OpaqueId): pass
class EndpointId(OpaqueId): pass
class CanonicalModelId(OpaqueId): pass
class ProviderModelId(OpaqueId): pass
class RuntimeRunId(OpaqueId): pass
class RuntimeSessionId(OpaqueId): pass
class WorkerId(OpaqueId): pass
class RouteLockId(OpaqueId): pass
class RouteAttemptId(OpaqueId): pass
class ExternalRequestId(OpaqueId): pass
```

### 2.3 Identification Invariants
* No generic `to_uuid()` methods on `OpaqueId` or base classes.
* Invalid UUID strings raise `IdentityValidationError` during instantiation.
* IDs are generated explicitly in domain aggregate factories or create commands, never implicitly during JSON deserialization of missing fields.

---

## 3. Canonical Workflow Specification

`WorkflowDefinition` in `windagent_core` is graph-based (nodes and edges), supporting complex DAG structures, fan-out/fan-in, conditional branching, and dependencies.

```python
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from windagent_core.domain.types import WorkflowId, StepId

class WorkflowNode(BaseModel):
    id: StepId
    name: str
    tool_name: str
    parameters: Dict[str, str] = Field(default_factory=dict)
    priority: int = 0
    timeout_seconds: Optional[float] = None
    max_attempts: int = 3
    
    model_config = ConfigDict(frozen=True, extra="forbid")

class WorkflowEdge(BaseModel):
    source_step_id: StepId
    target_step_id: StepId
    condition: Optional[str] = None
    edge_type: str = "dependency"  # dependency, conditional, compensation
    
    model_config = ConfigDict(frozen=True, extra="forbid")

class WorkflowDefinition(BaseModel):
    id: WorkflowId
    name: str
    version: int
    nodes: Dict[StepId, WorkflowNode]
    edges: List[WorkflowEdge]
    
    model_config = ConfigDict(frozen=True, extra="forbid")
```

> **Note**: An `order` property on a step is strictly a derived projection for UI rendering and legacy compatibility, NOT a canonical execution invariant.

---

## 4. Provider & Model Interaction Contracts

Core owns the domain models for model requests and responses exchanged across providers, intelligence, and orchestration:

```python
class CanonicalModelRef(BaseModel):
    provider_id: ProviderId
    model_id: CanonicalModelId

class ModelUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ModelRequest(BaseModel):
    request_id: ExternalRequestId
    model_ref: CanonicalModelRef
    messages: List[Dict[str, str]]
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    tools: List[Dict[str, str]] = Field(default_factory=list)

class ModelResponse(BaseModel):
    request_id: ExternalRequestId
    model_ref: CanonicalModelRef
    content: Optional[str] = None
    tool_calls: List[Dict[str, str]] = Field(default_factory=list)
    usage: ModelUsage
    finish_reason: str
```

---

## 5. Duplicate Model Disposition Matrix

Every model class across the workspace is assigned an explicit disposition:

| Model / Class Name | Original Package / Location | Proposed Canonical Disposition | Ownership Rationale & Action Plan |
| :--- | :--- | :--- | :--- |
| `WorkflowDefinition` (Ordered steps) | `core/domain/models.py` | **MOVE_TO_CORE** | Replaced with Graph-based (Nodes & Edges) `WorkflowDefinition`. |
| `WorkflowDefinition` (Graph DAG) | `orchestration/workflow_engine/definition.py` | **MOVE_TO_CORE** | Promoted to `windagent_core/domain/workflow.py` as canonical DAG representation. |
| `ModelRequest` / `ModelResponse` | `core/domain/models.py` | **MOVE_TO_CORE** | Consolidated in `windagent_core/domain/model.py` for cross-boundary usage. |
| `ProviderRequest` / `ProviderResponse` | `providers/domain/models.py` | **MAP_TO_CORE** | Converted to core `ModelRequest`/`ModelResponse` via provider adapters. |
| `TaskStatus` (subset) | `core/domain/models.py` | **REMOVE** | Replaced by canonical 15-state `TaskState` in `core/domain/lifecycle.py`. |
| `TaskState` (15 states) | `orchestration/state_machine/task.py` | **MOVE_TO_CORE** | Promoted to `windagent_core/domain/lifecycle.py` as sole canonical TaskState. |
| `EventEnvelope` | `core/events/envelope.py` | **MOVE_TO_CORE** | Canonical event envelope for all subsystems. |
| `LegacyEventDict` | `orchestration/events.py`, `backend/services/event_bus.py` | **MAP_TO_CORE** | Converted exclusively at API/WebSocket edge adapters. |
| `BaseEntityId` | `core/domain/types.py` | **REMOVE** | Replaced by `UUIDEntityId` and `OpaqueId`. |
| `ProviderFailure` | `providers/errors.py` | **MAP_TO_CORE** | Refactored to inherit from `windagent_core.errors.ProviderError`. |
| `FeatureFlagsManager` | `core/config/feature_flags.py` | **KEEP_CONTEXT_LOCAL** | Moved out of core to `apps/api/bootstrap` / application root. |
| `ShadowExecutionEngine` | `core/config/shadow_comparator.py` | **KEEP_CONTEXT_LOCAL** | Moved to `windagent_verification` package. |
