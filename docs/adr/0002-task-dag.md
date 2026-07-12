# ADR 0002: Task DAG (Directed Acyclic Graph) Scheduler and Versioning

## Status
Accepted

## Context
The current workflow implementation uses a linear list of steps (`WorkflowStepORM`), which doesn't support concurrency, sub-agent dispatching, parent-child task hierarchy, or dependencies between tasks. To scale to a multi-agent system, we need a robust DAG representation of tasks, a parallel scheduler, a comprehensive task state machine, and a versioning system to handle plan modifications during execution.

## Decision
We will replace the linear workflow list with a Task DAG model.

### 1. Data Models
- **`parent_tasks`**: Represents the overall objective. Contains `conversation_id`, `objective`, `status`, and `active_plan_version`.
- **`task_plans`**: Represents a specific version of a plan. Plan editing generates a new version (incrementing `version`) to ensure optimistic locking and auditable history.
- **`task_nodes`**: Represents individual tasks (e.g., Code Backend, Run tests). Contains required capabilities, assigned agent, status, retries, and inputs/outputs contract.
- **`task_edges`**: Represents directed dependency links between task nodes (`requires`, `blocks`, `soft_dependency`, `artifact_dependency`).
- **`task_artifacts`**: Captures outputs of a task (e.g., commit hash, patch files, logs).

### 2. State Machine
Every task node follows this state transition diagram:
```
       [draft]
          │
          ▼
   [blocked / ready]
          │
          ▼
      [assigned]
          │
          ▼
       [running]
       /   │   \
      /    │    \
     ▼     ▼     ▼
[waiting] [failed] [completed]
[approval]  │
     │      ▼
     │   [retryable]
     ▼
[cancelled]
```

### 3. DAG Scheduler Invariant
The scheduler resolves ready nodes asynchronously:
- A node moves from `blocked` to `ready` if and only if all its mandatory dependencies are in `completed` state and required input artifacts exist.
- Executing tasks must respect concurrency groups (`concurrency_group`) and permission limits.

### 4. Dynamic Re-planning and Versioning
- Users or the Orchestrator can modify the plan while it is executing.
- Each edit request must specify `expected_plan_version` to prevent write collision (optimistic lock).
- When a plan is updated, backend creates a new plan version, validates that the updated graph is a DAG (no cycles), determines which tasks are affected, cancels running tasks that were deleted, and triggers a replan event.

## Consequences
- **Concurrency**: Multiple sub-agents can execute independent tasks in parallel.
- **Traceability**: All execution artifacts are directly linked to the generating task node.
- **Safety**: Plan modification does not cause run corruption due to version tracking.
- **Robustness**: Task failures are handled cleanly with local retries instead of failing the entire session.
