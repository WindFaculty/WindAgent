# Orchestration V2 Architecture & Runtime Flow

## Overview
Orchestration V2 (`windagent_orchestration`) is the sole production orchestration runtime for `WindFaculty/WindAgent`.
It provides durable task state management, DAG workflow execution, bounded priority scheduling, atomic step dispatch leases, error classification & retries, and startup recovery with destructive replay protection.

---

## Bounded Context Subpackages

```text
orchestration/windagent_orchestration/
├── composition.py              # Composition Root & Container
├── ports.py                    # Contract Ports & Protocols
├── commands.py                 # CQRS Commands
├── queries.py                  # CQRS Queries
├── events.py                   # Domain Events & Outbox Payloads
├── metrics.py                  # Performance Gate Collector
│
├── task_manager/               # Durable Task State Facts & Transitions
├── workflow_engine/            # DAG Graph, Validator, Fan-out/in, Checkpoints
├── state_machine/              # Explicit 15-State Transition Table
├── scheduler/                  # Min-Heap Priority Queue, Locks & Event Wakeup
├── dispatcher/                 # Atomic Leases, Idempotency & Worker Registry
├── retry/                      # Error Classification, Exponential Backoff, Deadlines
└── recovery/                   # Crash Reconciler & Destructive Replay Guard
```

---

## Key Runtime Flows

### 1. Task Enqueue & State Transition
1. Client submits task creation command.
2. `TaskManager` records durable facts in `task_runs` table with version 1.
3. State transitions validate against `TaskStateMachine` explicit matrix (`ALLOWED_TRANSITIONS`).
4. Atomically commits state mutation and outbox event in single UnitOfWork.

### 2. Workflow DAG Execution & Checkpointing
1. `WorkflowEngine` initializes run, validates DAG using iterative Kahn's algorithm $O(V+E)$, and identifies root ready nodes.
2. Completing a step triggers fan-out child evaluation and fan-in gate checks (all parent steps completed).
3. Evaluates conditional edge predicates.
4. Atomically persists checkpoint state in `workflow_checkpoints` table.

### 3. Priority Scheduling & Zero-Busy-Poll Wakeup
1. `TaskScheduler` enqueues ready runs into `TaskPriorityHeap` (`heapq`).
2. `ProjectLockManager` prevents worktree/project collisions.
3. `EventDrivenWakeup` uses `asyncio.Event` notification, maintaining **0 ms busy-polling** and **<0.1% idle CPU**.

### 4. Step Dispatch & Atomic Lease Deduplication
1. `StepDispatcher` acquires atomic lease in `execution_leases` table.
2. Enforces unique `idempotency_key` (`run_id:step_id`).
3. Prevents duplicate claims across distributed workers.

### 5. Error Classification & Retry Policy
1. Evaluates `ErrorClassifier.is_retryable(exc)`.
2. **Fail-Closed**: Unclassified standard exceptions default to non-retryable.
3. Computes exponential backoff delay with cap and optional jitter.

### 6. Crash Recovery & Destructive Replay Guard
1. `RecoveryManager` scans in-flight runs on boot.
2. **Preserves original run ID**.
3. Inspects event history for destructive tools (`write_file`, `exec_shell`, `git_commit`, `git_push`, `delete_file`).
4. Interrupted destructive steps are marked `FAILED` to prevent unsafe replay.
