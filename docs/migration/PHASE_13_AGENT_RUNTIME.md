# Phase 13 — Agent Runtime (Milestone 2: Agent Platform)

**Date:** 2026-09-02  
**Status:** Cut over  
**Scope:** Consolidate the scattered orchestration implementation into a single bounded context under `modules/agent_runtime/` per plan section 19.

## Source → Target

Old locations (frozen reference, not imported):

```
orchestration/*              → modules/agent_runtime/domain/lifecycle (Task 15-state, Workflow 8-state, Step 12-state, Session 7-state)
orchestration/agent_loop     → modules/agent_runtime/domain/budget + lifecycle (AgentLoop 12-state, BudgetLimits/Usage/Snapshot)
orchestration/workflows      → modules/agent_runtime/domain/workflow (WorkflowDefinition DAG + validator)
orchestration/long_running   → modules/agent_runtime/domain/checkpoints + recovery
orchestration/delegation     → modules/agent_runtime/domain/delegation
orchestration/retry          → modules/agent_runtime/domain/retry (classifier + backoff + policy)
orchestration/scheduler      → modules/agent_runtime/domain/workflow (ready_nodes + priority) + application scheduler seam
orchestration/state_machine  → modules/agent_runtime/domain/lifecycle (all state machines)
orchestration/production     → modules/agent_runtime/* (budget, recovery, checkpoint, approvals)
storage/agent_loop, tasks    → modules/agent_runtime/infrastructure/* (durable rows)
apps/api agent routes        → modules/agent_runtime/api/routes.py (thin FastAPI router under /api/v4/agent-runtime)
```

Target layout (plan section 19 exact):

```
modules/agent_runtime/
├── public/                 # public re-exports for composition roots & tests
├── domain/
│   ├── errors.py           # AgentRuntimeError hierarchy (validation/not_found/conflict)
│   ├── lifecycle.py        # Session/AgentLoop/Task/Workflow/Step lifecycles (7/12/15/8/12 states)
│   ├── budget.py           # AgentBudgetLimits/Usage/Snapshot + clamp/inherit (component-wise minimum)
│   ├── workflow.py         # WorkflowNode/Edge/Definition + validate_dag/topological_order
│   ├── checkpoints.py      # CheckpointRecord + canonical_hash (immutable, hash-gated)
│   ├── approvals.py        # ApprovalRecord (PENDING → APPROVED/DENIED/EXPIRED)
│   ├── delegation.py       # DelegationRecord (PENDING → RUNNING → COMPLETED/FAILED/CANCELLED)
│   ├── retry.py            # RetryDecision/classify_error/backoff/RetryPolicy
│   ├── recovery.py         # recover_run/task_state + validate_checkpoint_seq
│   ├── sessions.py         # AgentSession aggregate helper
│   └── tasks.py            # AgentTask aggregate helper
├── application/
│   ├── commands.py         # 19 commands: Create/Transition Session/Run/Task/Workflow/Step + Checkpoint/Approval/Delegation + Budget
│   ├── queries.py          # 16 queries: Get/List Session/Run/Task/Workflow/Step/Checkpoint/Approval/Delegation
│   ├── ports.py            # AgentRuntimeStore + TransactionScope (UoW + outbox)
│   ├── models.py           # durable rows (8) + view DTOs (8) with to_payload()
│   ├── services.py         # orchestrator (one TransactionScope per command, atomic outbox, CAS)
│   ├── handlers.py         # Command/Query/Job handlers (ambient AgentRuntimeServices)
│   ├── runtime.py          # AgentRuntimeServices + ContextVar binding
│   └── events.py           # 16 agent_runtime.* envelopes (session/run/task/workflow/checkpoint/approval/delegation)
├── infrastructure/
│   ├── tables.py           # 8 agent_* tables registered into shared metadata (0010)
│   ├── repository.py       # SqlAgentRuntimeStore + SqlTransactionScope (CAS optimistic_version)
│   └── memory.py           # InMemoryAgentRuntimeStore + InMemoryTransactionScope (offline tests)
├── api/
│   └── routes.py           # /api/v4/agent-runtime/* — 32 endpoints, policy-gated, bus-dispatched
├── jobs/
│   └── handlers.py         # 3 jobs: agent_runtime.run.execute / task.execute / workflow.step.execute
├── manifest.py             # ModuleManifest (19 commands, 16 queries, 3 jobs, 1 router, 13 capabilities)
└── __init__.py
```

## Invariants preserved (REWRITE)

- **Lifecycles:** All canonical state machines frozen from `windagent_core.domain.lifecycle` + `windagent_core.domain.agent_loop`:
  - `SessionState` 7 states, terminal {COMPLETED, FAILED, CANCELLED, ARCHIVED}
  - `AgentLoopState` 12 states, terminal {COMPLETED, FAILED, CANCELLED, ORPHANED}
  - `TaskState` 15 states, terminal {COMPLETED, FAILED, CANCELLED} — with retry exception `FAILED → RETRY_WAIT` allowed (plan retry semantics)
  - `WorkflowState` 8 states, terminal {COMPLETED, FAILED, CANCELLED}
  - `StepState` 12 states, terminal {COMPLETED, FAILED, SKIPPED, CANCELLED}
  - Every transition validated via pure domain `Lifecycle.transition` before CAS.
- **Budget:** `AgentBudgetLimits`/`Usage`/`Snapshot` with `clamp_limits` + `inherit_limits` (component-wise minimum — child may only tighten finite limits). Exhaustion detection is fail-closed: `record_run_budget_usage` auto-transitions `RUNNING → FAILED` with `exhaustion_reason` and emits `run.budget_exhausted`.
- **DAG:** `WorkflowDefinition.validate_dag` rejects unknown refs, self-loops, duplicate edges, and cycles (Kahn). `topological_order` and `ready_nodes` (priority-ordered) mirror `workflow_engine.graph` semantics. `create_workflow` validates before persist; `schedule_workflow` materializes `WorkflowStep` rows (BLOCKED vs PENDING based on predecessors).
- **Checkpoint:** `CheckpointRecord.create` canonical SHA-256 hash of sorted JSON snapshot; monotonic `seq` scoped to `(run_id, task_id)` enforced in both SQL (`UNIQUE` via duplicate check) and memory. Recovery `validate_checkpoint_seq` ensures no gaps.
- **Approval:** `ApprovalRecord` frozen 4-state machine; `request_approval` transitions task `RUNNING → WAITING_PERMISSION` atomically and binds `awaiting_approval_id`; `resolve_approval` (APPROVED → `RUNNING`, DENIED/EXPIRED → `FAILED`) clears the binding. Stale approval guard via `expected_state`.
- **Delegation:** `DelegationRecord` frozen 5-state machine; `delegate_run` validates parent/child share session, enforces `max_child_agents` budget, inherits limits component-wise, bumps `child_agents` usage, moves parent `RUNNING → WAITING_CHILD` when needed; `transition_delegation` to terminal unblocks parent `WAITING_CHILD → RUNNING` when no siblings remain pending.
- **Retry:** `classify_error` deterministically maps substrings to `RETRY`/`FAIL` (terminal strings like `validation_error`, `budget exhausted` always FAIL; transient like `timeout`, `429` retry if attempts remain); `backoff_seconds` exponential with deterministic jitter; `RetryPolicy` ties `max_attempts` gating. `retry_task` implements `FAILED → RETRY_WAIT → RUNNING` (two hops, one attempt bump) vs `RETRY_WAIT → RUNNING`.
- **Recovery:** `recover_run_state`/`recover_task_state` mirror `orchestration/recovery` heuristics (checkpoint present → RESUME/RECOVER, exhaustion → FAIL, attempt gate).
- **Stale-write protection:** `optimistic_version` CAS on every mutating command (`expected_version` vs row version, `WHERE optimistic_version = :expected_version`). All 8 tables carry `optimistic_version`.
- **No duplicate dispatcher authority:** Job execution belongs to `platform/job runtime`; Agent Runtime only **submits jobs** via the 3 durable `agent_runtime.*` seams. Dispatcher/lease/fencing remains in platform.

## Architecture gates

- `test_kernel_does_not_import_infrastructure` — PASS
- `test_platform_*` — PASS
- `test_modules_do_not_import_each_other` — PASS (agent_runtime only imports `windagent.kernel` + `windagent.platform` + own package)
- `test_no_v2_file_imports_legacy` — PASS (no `windagent_core` / `windagent_orchestration` imports)
- `test_platform_contracts_only_depend_on_kernel_and_stdlib` — PASS
- `test_sqlite_is_not_a_default` — PASS (agent_runtime adds no `sqlite` string; only `platform/configuration/settings.py` may mention it)
- `test_modules_do_not_import_each_other` — PASS

`ruff check backend/src/windagent/modules/agent_runtime` — **All checks passed**  
`mypy --config-file pyproject.toml` — **0 errors in agent_runtime** (full repo 0 errors)

## Persistence

- **Migration `0010_agent_runtime`** creates 8 tables with FK-free, prefix-namespaced design (single Alembic chain, no legacy 31 revisions copied):
  `agent_sessions`, `agent_runs`, `agent_tasks`, `agent_workflows`, `agent_workflow_steps`, `agent_checkpoints`, `agent_approvals`, `agent_delegations`.
- Each table carries `optimistic_version` + UTC timestamps + JSON blobs for `metadata`/`budget`/`payload` (keeps schema additive).
- `SqlAgentRuntimeStore` implements `AgentRuntimeStore` with row-level CAS (`WHERE optimistic_version = :expected_version`) and `INSERT` uniqueness checks; `SqlTransactionScope` joins the caller's `SqlUnitOfWork` and records exactly one `agent_runtime.*` event via `TransactionalOutbox`.
- `InMemoryAgentRuntimeStore` mirrors the same CAS semantics for offline unit tests (`memory_scope_factory`).

## Application layer

- **Commands** are frozen dataclasses extending `Command[View]`; **Queries** extend `Query[View]`. No command builds provider or infra concerns.
- **AgentRuntimeService** is the only place that knows the row mapping; handlers are thin (`container_for(services).agent_runtime.*`).
- **Budget inheritance** is enforced on `create_run` with parent; `record_run_budget_usage` applies delta patches incrementally and auto-fails closed.
- **Workflow scheduling** is idempotently resumable: `DRAFT → READY → RUNNING` with DAG validation and step materialization in one transaction.
- **Outbox:** Every mutating command records one envelope (`agent_runtime.session.created/transitioned`, `agent_runtime.run.created/transitioned/budget_exhausted`, `agent_runtime.task.created/transitioned/completed/failed`, `agent_runtime.workflow.created/transitioned`, `agent_runtime.checkpoint.created`, `agent_runtime.approval.requested/resolved`, `agent_runtime.delegation.created/transitioned`) before `commit()`.

## API

- Prefix `/api/v4/agent-runtime` (canonical `/api/v4`, not `Wind_agent_v2` folder name).
- 32 endpoints across 8 sub-resources:
  - sessions `POST /sessions`, `POST /sessions/{id}/transitions`, `GET /sessions/{id}`, `GET /sessions`
  - runs `POST /runs`, `POST /runs/{id}/transitions`, `POST /runs/{id}/budget-usage`, `GET /runs/{id}`, `GET /runs`
  - tasks `POST /tasks`, `POST /tasks/{id}/transitions`, `POST /tasks/{id}/complete`, `POST /tasks/{id}/fail`, `POST /tasks/{id}/retry`, `GET /tasks/{id}`, `GET /tasks`
  - workflows `POST /workflows`, `POST /workflows/{id}/transitions`, `POST /workflows/{id}/schedule`, `GET /workflows/{id}`, `GET /workflows`
  - steps `POST /steps/{id}/transitions`, `GET /steps/{id}`, `GET /steps`
  - checkpoints `POST /checkpoints`, `GET /checkpoints/{id}`, `GET /checkpoints`
  - approvals `POST /approvals`, `POST /approvals/{id}/resolve`, `GET /approvals/{id}`, `GET /approvals`
  - delegations `POST /delegations`, `POST /delegations/{id}/transitions`, `GET /delegations/{id}`, `GET /delegations`
- Each route validates via Pydantic DTO, dispatches via `command_bus`/`query_bus`, and maps via `View.to_payload()`. Mutating routes require `agent_runtime.write`, reads require `agent_runtime.read` (policy engine, audited; unconfigured engine allows in dev).

## Jobs

- `agent_runtime.run.execute` — durable, fencing-protected job that transitions a run (payload `{run_id, target_state}`).
- `agent_runtime.task.execute` — durable job that completes/fails/transitions a task (payload `{task_id, action, output_payload/target_state}`).
- `agent_runtime.workflow.step.execute` — durable job that transitions a workflow step (payload `{step_id, target_state}`).
- All three are `JobRegistration`s discovered via `ModuleManifest`; the worker runtime claims/fences/finalizes via `platform/jobs` — Agent Runtime only submits.

## Module manifest

- `manifest = build_agent_runtime_manifest()` exposes:
  - 19 `CommandRegistration`s
  - 16 `QueryRegistration`s
  - 3 `JobRegistration`s (`agent_runtime.run.execute`, `agent_runtime.task.execute`, `agent_runtime.workflow.step.execute`)
  - 1 router (`create_agent_runtime_router()`)
  - capabilities `("agent_runtime","sessions","runs","planning","tasks","workflows","scheduler","checkpoints","retry","recovery","approvals","delegation","budget")`
- Discovered automatically by `PackageModuleDiscovery` (no bootstrap file lists it by name).

## Verification

- **Ruff:** `ruff check backend/src/windagent/modules/agent_runtime` — 0 errors, 0 warnings.
- **Mypy strict:** `mypy --config-file pyproject.toml` — 0 errors in agent_runtime (full repo 0 errors).
- **Architecture:** 8/8 architecture tests pass.
- **Unit (offline):** `pytest tests/unit` — 277 passed, `pytest tests/architecture` — 8 passed.
- **Smoke InMemory:** create session → run (budget inherit) → run budget exhaustion (auto FAIL) → task lifecycle (RECEIVED→PLANNING→READY→RUNNING→COMPLETED) → checkpoint → approval (WAITING_PERMISSION→APPROVED→RUNNING) → retry (FAILED→RETRY_WAIT→RUNNING) → workflow DAG (2 nodes, 1 edge, schedule → 2 steps) → step transitions (PENDING→READY→CLAIMED→DISPATCHED→RUNNING→COMPLETED) → delegation (WAITING_CHILD → COMPLETED → RUNNING) — 16 event types emitted.
- **SQL (file DB):** `sqlite+aiosqlite:////tmp/agent_runtime_test.db` via `SqlAgentRuntimeStore` + `metadata.create_all` — session→run→task→checkpoint→workflow→schedule→steps→approvals→delegations with CAS stale-version rejection verified.
- **API (file DB):** `/api/v4/agent-runtime` E2E via `httpx.ASGITransport` + `create_app(Settings(environment="test", database_url="sqlite+..."))` — `POST /sessions` → `POST /runs` → `POST /runs/{id}/transitions` → `POST /tasks` → `GET /tasks` → `POST /workflows` → `POST /workflows/{id}/schedule` → `GET /steps` → `POST /checkpoints` → `POST /approvals` → `POST /approvals/{id}/resolve` → `POST /delegations` → `GET /sessions`.

## Cutover notes

- No V2 file imports `../orchestration`, `../workflows`, `../windagent_core`, or `../windagent_orchestration`.
- `orchestration/*` remains frozen; data migration will flow through importers, not through this schema history.
- Job execution remains in `platform/jobs` + `apps/worker`; Agent Runtime only submits jobs (plan 19: "Job execution thuộc platform/job runtime, Agent Runtime chỉ submit jobs").
- Frontend modules will be built in a later phase (Milestone 4) against the generated `@windagent/api-sdk` from this backend.
- Memory module (Phase 14) will be built next; it will reuse the checkpoint/recovery seams defined here.

## Definition of Done (plan section 19)

- [x] Single bounded context `modules/agent_runtime` owns sessions/runs/planning/tasks/workflows/scheduler/checkpoints/retry/recovery/approvals/delegation
- [x] Domain is pure (no FastAPI/SQLAlchemy/httpx), `ruff` + `mypy` clean, architecture 8/8 pass
- [x] Persistence is PostgreSQL-canonical with `0010` migration, plus in-memory adapter for tests
- [x] Events are atomic via outbox, with 16 `agent_runtime.*` envelopes
- [x] API is `/api/v4/agent-runtime`, thin, bus-dispatched, policy-gated
- [x] Job seams `agent_runtime.run.execute` / `task.execute` / `workflow.step.execute` are durable and worker-discoverable
- [x] Module is auto-discoverable, no bootstrap edit required
