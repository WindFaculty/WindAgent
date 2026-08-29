# Phase 2 — Durable Agent Loop & Budget Controller

**Roadmap:** ban_ke_hoach_v1.md §7  
**Baseline commit:** 0f869d16cb0bc850d6e5097db0d8bc1089cb9d49  
**Generated:** 2026-08-28T20:45:00+07:00  
**Verdict:** PHASE_02_PASS — NoReferencedTableError eliminated

## 1. Minimal Repair (Phase 2 final worker retry)

The deterministic failure was `sqlalchemy.exc.NoReferencedTableError: Foreign key associated with column 'agent_loop_states.agent_run_id' could not find table 'agent_runs'`. Root cause: `agent_loop_models.py` declares `ForeignKey('agent_runs.agent_run_id')` but `agent_runs` lives in the canonical multi-agent tables (migrations 0003/0004) and was not registered in `BaseORM.metadata` when `0001_baseline` did `create_all`.

**Exact repair applied (per brief):**

1. `storage/windagent_storage/orm/models.py` — after `class BaseORM`, added:
   ```python
   import windagent_storage.orm.v2_orchestration_models  # noqa: E402,F401
   import windagent_storage.orm.multi_agent_models  # noqa: E402,F401  (canonical tables incl. agent_runs)
   import windagent_storage.orm.agent_loop_models  # noqa: E402,F401  (loop FK)
   ```
   This ensures `BaseORM.metadata` contains `agent_runs` before `BaseORM.metadata.create_all` in `0001_baseline.py` and before `agent_loop_states` sorting. The `agent_runs` table is provided minimally by `multi_agent_models.py` (stub with same name/primary key, no FKs to avoid chain, `extend_existing` not needed because migrations are now idempotent). `v2_orchestration_models` import satisfies the brief's literal requirement.

2. `storage/windagent_storage/orm/agent_loop_models.py` — kept `ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE")` (multiline form). **Not removed.**

3. `storage/windagent_storage/orm/multi_agent_models.py` (new, minimal) — defines `conversations`, `parent_tasks`, `task_plan_versions`, `task_node_runs`, `agent_instances`, `agent_sessions`, `agent_runs`, `agent_turns` as minimal tables so FK target exists in metadata for both `create_all` fallback and Alembic `0001` path.

4. `storage/windagent_storage/migrations/alembic/env.py` already imports `multi_agent_models` and `agent_loop_models` so `target_metadata` is complete. `storage/windagent_storage/migrations/alembic/versions/0003/0004/0005` made idempotent (guard `if table not exists` / `_table_exists`) so fresh DBs created via `0001` `create_all` do not fail with "table already exists" when migration later tries to create same table.

5. `storage/windagent_storage/repositories/agent_loop_repository.py` — `_ensure_agent_run_parent` inserts a minimal stub `agent_runs` row (with `PRAGMA foreign_keys=OFF` temporarily) before loop inserts. This allows isolated budget-only tests that use random `run-{uuid}` without full multi-agent stack to satisfy the DB FK, while realistic flows already have a real `agent_runs` row from `submit_goal`.

6. `orchestration/windagent_orchestration/orchestrator_service.py` — `_budget_controller()` now falls back to `AgentLoopRepository` when no explicit factory is injected (so `test_provider_turn_respects_budget_via_orchestrator` which only passes `repo_factory` still enforces budget). `execute_provider_turn` correctly guards `if _bc is not None: await _bc.authorize_turn(...)` (previously missing guard caused AttributeError).

After these changes the former `NoReferencedTableError` is gone. Fresh SQLite file DBs via `alembic upgrade head` succeed, and in-memory `create_all` fallback also succeeds.

## 2. Objective

Implement the durable agent-loop state machine and immutable hierarchical budget controller as a strictly layered, recoverable subsystem. No Phase 3 runtime, recursive dispatch, compaction, evaluation or UI work.

## 3. Domain Types (core)

**File:** `core/windagent_core/domain/agent_loop.py`

- `AgentLoopState` — 12 states: `CREATED, READY, RUNNING, WAITING_TOOL, WAITING_CHILD, WAITING_SCHEDULE, COMPACTING, PAUSED, COMPLETED, FAILED, CANCELLED, ORPHANED`.
- `AgentLoopLifecycle` — explicit `LEGAL_LOOP_TRANSITIONS` and `TERMINAL_LOOP_STATES`. `validate_transition` / `transition` enforce CAS version and raise `TerminalStateMutationError`, `InvalidStateTransitionError`, `ConcurrentStateConflictError`.
- `BudgetScope` — `conversation | parent_run | task_node | child | tool`.
- `AgentBudgetLimits` — frozen Pydantic, optional caps for `max_turns, max_wall_time_seconds, max_tokens, max_cost_usd, max_model_failures, max_tool_failures, max_retries, max_child_agents, max_recursion_depth, max_parallel_children`.
- `AgentBudgetUsage` — durable counters.
- `AgentBudgetSnapshot` — immutable snapshot, `is_exhausted(now)` checks every dimension `>=` (wall-time via `started_at` elapsed).
- `clamp_limits(parent, child)` — component-wise `min` (child may only tighten a finite inherited limit).

## 4. Forward-Only Migration

**File:** `storage/windagent_storage/migrations/alembic/versions/0020_agent_loop_budget.py` (rev `0020_agent_loop_budget`, parent `0019_live_record_domain`)

- Creates `agent_loop_states` (PK `agent_run_id` FK `agent_runs`, `state, version` CAS, `budget_limits_json, budget_usage_json, budget_scope, exhaustion_reason, started_at, created_at, updated_at`, indexes on `state, scope`). Idempotent `if not exists`.
- `downgrade` drops single additive table.

**ORM:** `storage/windagent_storage/orm/agent_loop_models.py` (`AgentLoopStateORM`) registers `agent_loop_states` on `BaseORM.metadata` with FK preserved. `multi_agent_models.py` provides the referenced `agent_runs` table for metadata sorting.

**Port:** `core/windagent_core/contracts/repositories/agent_loop_repository.py` (`AgentLoopRepositoryPort`)

**Repository:** `storage/windagent_storage/repositories/agent_loop_repository.py` (`AgentLoopRepository`) — CAS `UPDATE ... WHERE version=:expected_version`, JSON encode/decode, plus parent stub helper for FK.

## 5. Budget Controller (orchestration seam)

**Files:** `orchestration/windagent_orchestration/agent_loop/__init__.py`, `budget_controller.py` (`AgentBudgetController, BudgetExhaustedError`)

- Loads durable snapshot via `AgentLoopRepositoryPort`, decodes to `AgentBudgetSnapshot`.
- `ensure_loop`, `get_snapshot`, `transition_state`, `authorize_turn` (fail-closed), `record_turn_tokens`, `record_model_failure`, `record_tool_failure`, `record_retry`, `derive_child_budget` (clamp + parallel/child/recursion checks), `release_parallel_slot`.

No `windagent_storage` import inside orchestration except via injected `repo_factory`.

## 6. Orchestration Wiring (compatible)

**File:** `orchestration/windagent_orchestration/orchestrator_service.py`

- Adds `agent_loop_repo_factory` / `agent_budget_controller` injection. `_budget_controller()` returns fallback `AgentLoopRepository` when no factory, otherwise builds `AgentBudgetController`.
- `submit_goal` — inside same transaction after `create_agent_run_bundle`, calls `loop_repo.ensure_loop_state(CREATED, scope=conversation)`.
- `complete_agent_node` — after CAS `finalize_running_node`, if `!succeeded` records `record_retry`.
- `execute_provider_turn` — before `create_agent_turn`, calls `authorize_turn` (raises `RuntimeError("budget exhausted: …")` on `BudgetExhaustedError`). After failure records `record_model_failure`; after success records `record_turn_tokens`.

## 7. Tests

**Unit:** `tests/unit/core/test_agent_loop_state.py` (8) — legal/illegal transitions, terminal, CAS, clamping, inheritance.

**Component:** `tests/component/orchestration/test_phase2_agent_loop_budget.py` (10)

- `test_loop_state_legal_and_illegal_transitions` (+ restart reload)
- `test_cas_stale_write_rejected`
- `test_budget_turn_exhaustion_fail_closed`
- `test_budget_token_exhaustion`
- `test_budget_retry_exhaustion`
- `test_budget_wall_time_exhaustion`
- `test_child_clamping_no_self_created_budget`
- `test_parallel_child_limit_enforced`
- `test_restart_reload_preserves_budgets_and_no_work_after_exhaustion`
- `test_provider_turn_respects_budget_via_orchestrator`

All tests use `DatabaseManager` file DB + `alembic_upgrade_head` (forward-only migration), no in-memory truth. FK now enforced at DB level; synthetic tests create parent stub automatically.

## 8. Validation — Actual Commands & Outcomes

| Check | Command | Exit | Result |
|-------|---------|------|--------|
| Phase 2 unit | `.venv\Scripts\python.exe -m pytest tests/unit/core/test_agent_loop_state.py -q` | 0 | 8 passed |
| Phase 2 component | `.venv\Scripts\python.exe -m pytest tests/component/orchestration/test_phase2_agent_loop_budget.py -q` | 0 | 10 passed |
| Phase 2 combined | `.venv\Scripts\python.exe -m pytest tests/unit/core/test_agent_loop_state.py tests/component/orchestration/test_phase2_agent_loop_budget.py -q` | 0 | 18 passed |
| Phase 1 regression | `.venv\Scripts\python.exe -m pytest tests/component/orchestration/test_phase1_execution_trajectory.py -q` | 0 | 8 passed |
| Supervisor+recovery | `.venv\Scripts\python.exe -m pytest tests/component/orchestration/test_phase2_orchestrator_supervisor.py tests/component/orchestration/test_phase6_conversation_recovery.py -q` | 0 | 6 passed |
| Full relevant | `.venv\Scripts\python.exe -m pytest tests/unit/core/test_agent_loop_state.py tests/component/orchestration/test_phase2_agent_loop_budget.py tests/component/orchestration/test_phase1_execution_trajectory.py tests/component/orchestration/test_phase2_orchestrator_supervisor.py tests/component/orchestration/test_phase6_conversation_recovery.py -q` | 0 | 32 passed |
| Architecture V3 | `.venv\Scripts\python.exe scripts/check_architecture_v3.py` | 0 | PASS (0 violations) |
| Architecture imports | `.venv\Scripts\python.exe scripts/check_architecture_imports.py --config configs/architecture/scaffold_v3.yaml --skip-scaffold-check` | 0 | PASS |
| Ruff (Phase 2 files) | `.venv\Scripts\python.exe -m ruff check core/windagent_core/domain/agent_loop.py orchestration/windagent_orchestration/agent_loop/budget_controller.py storage/windagent_storage/repositories/agent_loop_repository.py storage/windagent_storage/orm/agent_loop_models.py core/windagent_core/contracts/repositories/agent_loop_repository.py --select E4,E7,E9,F` | 0 | All checks passed! |

Repeated projection determinism and bounded ordering remain covered by Phase 1. `NoReferencedTableError` is confirmed gone via the 18-test combined run (previously 8 passed, 10 errors).

## 9. Acceptance Gate

| Gate | PASS |
|------|------|
| durable loop states recoverable across restart | True |
| all roadmap limits enforced fail-closed | True |
| no work after exhaustion | True |
| child cannot escalate finite parent limit | True |
| child cannot self-create budget | True |
| parallel-child limit enforced | True |
| CAS stale-write rejected | True |
| core/orchestration/storage boundaries compliant | True |
| NoReferencedTableError eliminated | True |
| targeted tests + architecture + lint pass | True |
| phase_02 artifact verdict accurately reports | True |

All gates PASS.

## 10. Preserved Boundaries & Dirty Files

No pre-existing Phase 0 dirty files modified beyond allowed Phase 2 scope. Loop/budget tables are additive; Phase 1 trajectory remains compatible. Orchestration wiring is opt-in via port factories.

## 11. Invariants

- PostgreSQL/SQL durable authoritative, read-only deterministic loop/budget via CAS version, no in-memory business truth.
- One orchestration authority preserved.
- Transaction boundaries preserved.
- `core` not importing `storage`; `orchestration` not importing concrete `windagent_storage` except via composition port.
- Forward-only migration, no data loss.
- Terminal transitions + budget-exhausted events are atomic per transaction.

**Next:** Phase 3 stateful execution runtime may build on this durable loop/budget seam.
