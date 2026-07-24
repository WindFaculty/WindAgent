# WindAgent Core Migration Map Specification

## 1. Overview

This document outlines the systematic migration strategy to transition all subsystems across WindAgent to the canonical `windagent_core` model.

---

## 2. Subsystem Migration Roadmaps

### 2.1 `windagent_orchestration`
* **Task State Machine**: Deprecate internal `TaskState` in `orchestration/state_machine/task.py`. Replace with `windagent_core.domain.lifecycle.TaskState`.
* **Workflow Engine**: Adopt graph-based `WorkflowDefinition` from `windagent_core.domain.workflow`. Remove internal node/edge duplicates.
* **Events**: Replace dict-based events with `windagent_core.events.envelope.EventEnvelope`.
* **RAM State Removal**: Replace internal `_facts` RAM dictionary in `TaskManager` with `windagent_storage` `TaskRepository` / `UnitOfWork`.

### 2.2 `windagent_providers`
* **Request/Response Models**: Map `ProviderRequest`/`ProviderResponse` to `windagent_core.domain.model.ModelRequest`/`ModelResponse`.
* **Error Hierarchy**: Refactor `ProviderFailure` exceptions to inherit from `windagent_core.errors.ProviderError`.

### 2.3 `windagent_storage`
* **Repository Implementation**: Update repositories to implement `windagent_core.contracts.TaskRepository`, `WorkflowRepository`, etc.
* **Database Schema Migrations**: Alembic migrations for 15-state TaskState enum constraints, stream sequence counters, and event schema versions.

### 2.4 `windagent_tools`
* **Security & Permissions**: Implement core `PermissionEvaluator` interface for tool executions.
* **Invocation Models**: Adopt core `ToolInvocation` and `ToolResult`.

### 2.5 `windagent_intelligence`
* **Gateway Port**: Implement `windagent_core.contracts.ModelGatewayPort`.

### 2.6 Edge Applications (`apps/api`, `apps/backend`, `apps/worker`, `apps/cli`)
* **API Routers**: Update endpoints to receive/return canonical core models.
* **Compatibility Layer**: Place legacy event/status mappers exclusively in `apps/api/adapters/` and `apps/backend/compatibility/`.

---

## 3. Comprehensive Model Disposition Table

| Class / Enum / Model | Source Location | Proposed Disposition | Target Canonical Location | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `TaskState` (15 states) | `orchestration/state_machine/task.py` | **MOVE_TO_CORE** | `core/windagent_core/domain/lifecycle.py` | Primary Task State Machine |
| `TaskStatus` (6 states) | `core/domain/models.py` | **REMOVE** | N/A | Replaced by 15-state TaskState |
| `WorkflowDefinition` (ordered) | `core/domain/models.py` | **REMOVE** | N/A | Replaced by Graph WorkflowDefinition |
| `WorkflowDefinition` (graph) | `orchestration/workflow_engine/definition.py` | **MOVE_TO_CORE** | `core/windagent_core/domain/workflow.py` | Primary Graph Workflow |
| `BaseEntityId` | `core/domain/types.py` | **REMOVE** | N/A | Replaced by UUIDEntityId & OpaqueId |
| `EventEnvelope` | `core/events/envelope.py` | **MOVE_TO_CORE** | `core/windagent_core/events/envelope.py` | Primary Event Envelope |
| `ProviderRequest` / `Response` | `providers/domain/models.py` | **MAP_TO_CORE** | N/A (Provider Adapters) | Converted to ModelRequest/Response |
| `ProviderFailure` | `providers/errors.py` | **MAP_TO_CORE** | N/A | Inherits from Core ProviderError |
| `FeatureFlagsManager` | `core/config/feature_flags.py` | **KEEP_CONTEXT_LOCAL** | `apps/api/bootstrap/feature_flags.py` | Moved out of core |
| `ShadowExecutionEngine` | `core/config/shadow_comparator.py` | **KEEP_CONTEXT_LOCAL** | `verification/windagent_verification/shadow.py` | Moved to verification |
