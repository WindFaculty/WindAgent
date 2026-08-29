# Phase 5 — Long-running Agent Hardening

**Roadmap:** `ban_ke_hoach_v1.md` §10  
**Baseline commit:** `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49`  
**Generated:** 2026-08-28T17:15:00+07:00  
**Verdict:** **PHASE_05_PASS**

---

## 1. Objective

Harden the long-running agent so a `goal` survives any volatile lifetime:

```
UI killed
API process killed
Worker killed
network partition
```

and every progress signal is durably checkpointed at **every mandated boundary**:

```
turn boundary
tool boundary
child admission
child completion
compaction
external wait
terminal state
```

Heartbeat carries two roles: `observability + control-plane liveness`.
`ProductionWorker` stays the independent process (no new daemon); Phase 5 makes its contract testably durable.

Target maturity after this phase: **MILESTONE A — Observable Durable Agent** (Phases 0/1/2/4/5).

---

## 2. Persistent Goal — durable long-running objective

### Domain — `core/windagent_core/domain/persistent_goal.py`

- `GoalStatus` — `ACTIVE, IN_PROGRESS, BLOCKED, PAUSED, COMPLETED, FAILED, CANCELLED`
- `TERMINAL_GOAL_STATES` — `COMPLETED, FAILED, CANCELLED`
- `LEGAL_GOAL_TRANSITIONS` — mirrors `AgentLoopLifecycle` with `ACTIVE` as entry, `PAUSED ↔ ACTIVE/IN_PROGRESS/BLOCKED` for human review, `BLOCKED` needs explicit `blocked_reason`
- `PersistentGoal` — frozen Pydantic snapshot with roadmap fields:

  ```
  goal_id
  objective
  status
  progress_summary
  started_at
  last_progress_at
  completion_criteria
  blocked_reason
  ```

  plus `conversation_id/parent_task_id/agent_run_id/harness_version/version/created_at/updated_at`

- `GoalLifecycle` — `is_terminal/can_transition/validate_transition/transition` CAS-guarded via `expected_version`, `TerminalStateMutationError` / `InvalidStateTransitionError` / `ConcurrentStateConflictError` (same exception taxonomy as Phase 2)

### Port — `core/windagent_core/contracts/repositories/persistent_goal_repository.py`

`PersistentGoalRepositoryPort`: `create_goal/get_goal/list_goals/update_progress/transition_status/update_completion_criteria`

### Storage — `storage/windagent_storage/orm/persistent_goal_models.py` + `repositories/persistent_goal_repository.py` + `migrations/0022_long_running_hardening.py`

- Table `persistent_goals` (`goal_id PK`, `objective`, `status`, `progress_summary`, `completion_criteria_json`, `blocked_reason`, `conversation_id`, `parent_task_id`, `agent_run_id`, `harness_version`, `version` CAS, `started_at`, `last_progress_at`, `created_at`, `updated_at`)
- Indexes on `conversation/parent/agent_run/status`
- Repository uses `UPDATE ... WHERE version=:expected_version` (0-1 row, CAS), decodes `completion_criteria_json → completion_criteria` dict, returns `None` on stale
- Migration `0022` forward-only, idempotent (`if not exists`), additive; `downgrade` drops both Phase-5 tables

### Orchestration — `orchestration/windagent_orchestration/long_running/goal_service.py`

- `GoalService` — narrow seam (session_factory + repo factory, no concrete storage import, no `orchestrator_service.py` bloat)
- `create_goal`: validates `objective`, allocates `goal_id`, persists `ACTIVE`, best-effort `persistent_goal_created` event via `MultiAgentRepository.append_event`
- `update_progress`: CAS `expected_version`, rejects terminal `COMPLETED/FAILED/CANCELLED`, appends `persistent_goal_progress` event
- `transition{,_blocked,_paused,_resumed,_completed,_failed,_cancelled}`: `GoalLifecycle.transition` CAS, then repo `transition_status`, then `persistent_goal_{status.lower()}` event; `BLOCKED` keeps `blocked_reason`, non-BLOCKED clears it
- `pause/resume` follow `PAUSED → ACTIVE → IN_PROGRESS` chain for reviewer workflow

---

## 3. Durable Checkpoints — every mandated boundary

### Domain — `core/windagent_core/domain/durable_checkpoint.py`

- `CheckpointKind` enum: `turn_boundary, tool_boundary, child_admission, child_completion, compaction, external_wait, terminal_state, manual, auto` (first 7 mandated by §10)
- `HOST_FORBIDDEN_KEYS` identical to Phase 3 substrate (`provider_credentials/credentials/api_key/secret/provider_call/schedule/memory_write/learning_promotion/host_authority...`) — checkpoints are substrate-only (defense-in-depth with Phase 3)
- `assert_no_host_authority / sanitize_snapshot / ensure_json_serializable` — fail-closed + stripping + JSON opaque guarantee
- `DurableCheckpoint` — frozen `checkpoint_id, agent_run_id, session_id, kind, step_run_id, tool_name, fencing_token, snapshot, sequence, loop_version_at_checkpoint, created_at`

### Port — `core/windagent_core/contracts/repositories/agent_checkpoint_repository.py`

`AgentCheckpointRepositoryPort`: `create_checkpoint/get_checkpoint/list_checkpoints/latest_checkpoint/count_checkpoints`

### Storage — `storage/windagent_storage/orm/agent_checkpoint_models.py` + `repositories/agent_checkpoint_repository.py`

- Table `agent_checkpoints` (`checkpoint_id PK`, `agent_run_id` index, `session_id`, `kind` index, `step_run_id`, `tool_name`, `fencing_token`, `snapshot_json`, `sequence` (per-agent monotonic), `loop_version_at_checkpoint`, `created_at`, composite indexes `run_seq` + `run_kind`)
- `create_checkpoint`: `_sanitize` (`assert_no_host_authority` + `sanitize_snapshot` + `ensure_json_serializable`), then `SELECT MAX(sequence)` in transaction, then `loop_version` from `agent_loop_states.version` (1 if no row), then `INSERT`, then `_decode` returns deep-copied `snapshot` (mutating returned dict cannot affect store — same immutability as Phase 3)
- `list/latest/count` ordered by `sequence` (deterministic replay order)

### Orchestration — `orchestration/windagent_orchestration/long_running/checkpoint_service.py`

- `CheckpointService` — validates `kind ∈ _VALID_KINDS` else `CheckpointError`, validates/sanitizes snapshot (deep-copy, stripped, JSON), allocates `checkpoint_id`, delegates to repo, best-effort `agent_checkpoint_{kind}` event via `conversation_id_for_agent` if available
- Convenience per-boundary: `at_turn_boundary, at_tool_boundary, at_child_admission, at_child_completion, at_compaction, at_external_wait, at_terminal_state` — each is a thin `kind=` wrapper so callers never pass a raw string incorrectly (turn/tool/child/compaction/wait/terminal all tested)

---

## 4. Heartbeat hardening — two roles

### Existing authority (kept)

`apps/worker/windagent_worker/runner.py` `ProductionWorker` already runs as independent process with `_heartbeat_loop` (every `heartbeat_interval_sec`), `record_heartbeat` writes `WorkerHeartbeat` to the repo, and renewal `task_queue.renew / lease_manager.renew_lease` with fencing-token mismatch → `cancel()` (control-plane liveness). No new `PrimeDaemon/AgentSchedulerV2` introduced.

### New testable hardening — `orchestration/windagent_orchestration/long_running/heartbeat.py`

- `HeartbeatHardening` — single-tick deterministic facade with same two roles:
  - **observability**: records `HeartbeatRecord(worker_id, runtime_run_id, active_leases, recorded_at, fencing_token, metadata)` into `_history`; `determinism_snapshot()` returns `{worker_id, runtime_run_id, ticks, cancelled_count, last_tick_at}` for restart assertions; optionally persists via `heartbeat_repo.record_heartbeat` (adapts to `WorkerHeartbeat`)
  - **liveness**: if `current_task_provider()->(task_id, fencing_token)` is set, renews via `task_queue.renew` or `lease_manager.renew_lease` (handles both async and sync lease managers — `await res if is-awaitable else res`); `False` → `fencing_rejected=True`, runs `cancellation_hook`, increments `cancelled_count`, returns `cancelled=True`
- Mirrors `ProductionWorker.record_heartbeat` logic so Phase-5 tests can prove the invariant without spawning a real worker process

---

## 5. Integration & kill-scenario determinism

- `persistent_goals` and `agent_checkpoints` are orthogonal to `execution_leases` fencing — checkpoints/goals survive lease expiry/takeover and survive a new `GoalService/CheckpointService` instance on the same DB (proved by `test_checkpoint_restart_visibility_and_lease_takeover` and `test_goal_restart_visibility`)
- `parent PAUSED` does not block child `checkpoint` or `publish_child_result` — compaction checkpoint can be written while parent is `PAUSED` and parent then resumes (`test_parent_pause_checkpoint_continues_and_survives_compaction`)
- Deterministic kill at every stage: the test `test_kill_scenarios_deterministic_state_after_restart` simulates `worker crash / API kill / network partition` between `turn → tool → child_admission → child_completion → compaction → external_wait → terminal`. After each simulated restart (new service instances), goals/checkpoints counts are exactly the durable rows (no duplication, no loss), `sequence` stays `0..6` monotonic, `kinds` stay in mandated order.

---

## 6. Tests — `tests/component/orchestration/test_phase5_long_running_hardening.py` (12 tests)

| Test | Covers |
|------|--------|
| `test_goal_create_and_progress` | create `ACTIVE` with `completion_criteria`, `IN_PROGRESS` transition, `update_progress` → `last_progress_at` |
| `test_goal_blocked_and_unblock_and_pause_resume` | `BLOCKED` with `blocked_reason`, `UNBLOCK→IN_PROGRESS` clears reason, `PAUSE→resume (ACTIVE/IN_PROGRESS)`, `COMPLETED` terminal rejects `update_progress/block` |
| `test_goal_lifecycle_illegal_and_terminal` | `COMPLETED→FAILED` illegal (TerminalStateMutation), CAS stale `version=1` `→ None` |
| `test_goal_restart_visibility` | new `GoalService` with same DB sees same `progress_summary/status`, can continue progressing after restart |
| `test_checkpoint_at_all_mandated_boundaries` | 7 mandated kinds × explicit `checkpoint` + 7 convenience `at_*` = 14 rows, `sequence 0..13`, per-kind filter |
| `test_checkpoint_immutability_and_json_serializable` | deep-copy on return and on input not leaking, `set` snapshot `→ ValueError` not JSON |
| `test_checkpoint_no_host_authority_and_sanitize` | 8 forbidden families rejected at every kind (nested too), `sanitize_snapshot` strips `secret/api_key` depth-2 |
| `test_checkpoint_checkpointed_at_loop_version` | `loop_version_at_checkpoint` tracks `agent_loop_states.version`, monotonic after `record_turn_tokens` |
| `test_checkpoint_restart_visibility_and_lease_takeover` | new `CheckpointService` sees prior rows, lease takeover does not lose checkpoints |
| `test_parent_pause_checkpoint_continues_and_survives_compaction` | parent `PAUSED` → child still checkpoints, parent compaction checkpoint while paused, then `RESUME` parent still `RUNNING` rows 2+1 |
| `test_kill_scenarios_deterministic_state_after_restart` | **Kill UI/API/Worker/network at each stage** — turn→tool→admission→completion→compaction→wait→terminal deterministic after restart (7 boundaries, ordered kinds, no duplication, goal `IN_PROGRESS` intact) |
| `test_heartbeat_two_roles_observability_and_liveness` | `active_leases` observability (0→1, history 2, snapshot ticks 2), fencing `False→cancel` (sync+async lease paths), `True→no cancel` |

Additional domain-level heartbeat contract is exercised without requiring a live `Worker` process (sync `FakeLease` + async `task_queue` paths both covered).

---

## 7. Validation — actual commands & outcomes

| Check | Command | Exit | Result |
|-------|---------|------|--------|
| Phase 5 component (12) | `python -m pytest tests/component/orchestration/test_phase5_long_running_hardening.py -v` | 0 | 12 passed |
| Combined 2+3+4+5 + unit (55) | `python -m pytest tests/unit/core/test_agent_loop_state.py tests/component/orchestration/test_phase2_agent_loop_budget.py tests/unit/execution/test_phase3_stateful_execution_runtime.py tests/component/orchestration/test_phase4_recursive_subagents.py tests/component/orchestration/test_phase5_long_running_hardening.py -v` | 0 | 55 passed |
| Architecture V3 (overall) | `python scripts/check_architecture_v3.py` | 0 | PASS (0 violations) |
| Architecture imports (overall) | `python scripts/check_architecture_imports.py --config configs/architecture/scaffold_v3.yaml --skip-scaffold-check` | 0 | PASS (0 violations) |
| Ruff Phase 5 files | `python -m ruff check core/windagent_core/domain/persistent_goal.py ... orchestration/windagent_orchestration/long_running/heartbeat.py --select E4,E7,E9,F` | 0 | All checks passed! |

The two pre-existing Phase-3 fallback violations (`orchestrator_service.py:241` → `AgentLoopRepository`) remain fixed from Phase 4 (0 violations scoped and overall).

---

## 8. Acceptance gate (Phase 5 §10)

| Gate | PASS |
|------|------|
| persistent goal (`goal_id/objective/status/progress_summary/started_at/last_progress_at/completion_criteria/blocked_reason`) | ✅ |
| durable checkpoints at `turn_boundary` | ✅ |
| durable checkpoints at `tool_boundary` | ✅ |
| durable checkpoints at `child_admission` | ✅ |
| durable checkpoints at `child_completion` | ✅ |
| durable checkpoints at `compaction` | ✅ |
| durable checkpoints at `external_wait` | ✅ |
| durable checkpoints at `terminal_state` | ✅ |
| heartbeat two roles: `observability + control-plane liveness` | ✅ |
| Worker/UI/API/network killed at each stage → state deterministic after restart (no lost progress, no duplicate sequence) | ✅ |
| no new daemon (ProductionWorker remains independent process) | ✅ |
| no in-memory business truth, forward-only migration, CAS-safe, fail-closed host-authority | ✅ |
| targeted tests + architecture/lint | ✅ |

All gates PASS.

---

## 9. Files changed (Phase 5)

**New (Phase 5):**
- `core/windagent_core/domain/persistent_goal.py`
- `core/windagent_core/domain/durable_checkpoint.py`
- `core/windagent_core/contracts/repositories/persistent_goal_repository.py`
- `core/windagent_core/contracts/repositories/agent_checkpoint_repository.py`
- `storage/windagent_storage/orm/persistent_goal_models.py`
- `storage/windagent_storage/orm/agent_checkpoint_models.py`
- `storage/windagent_storage/repositories/persistent_goal_repository.py`
- `storage/windagent_storage/repositories/agent_checkpoint_repository.py`
- `storage/windagent_storage/migrations/alembic/versions/0022_long_running_hardening.py`
- `orchestration/windagent_orchestration/long_running/__init__.py`
- `orchestration/windagent_orchestration/long_running/goal_service.py`
- `orchestration/windagent_orchestration/long_running/checkpoint_service.py`
- `orchestration/windagent_orchestration/long_running/heartbeat.py`
- `tests/component/orchestration/test_phase5_long_running_hardening.py`
- `artifacts/ban_ke_hoach_v1/phase_05/phase_05_verdict.json`
- `artifacts/ban_ke_hoach_v1/phase_05/PHASE_05_REPORT.md` (this file)

**Modified (narrow seams, additive only):**
- `storage/windagent_storage/orm/models.py` — add `persistent_goal_models/agent_checkpoint_models/multi_agent_models` imports for `BaseORM.metadata` fallback
- `storage/windagent_storage/migrations/alembic/env.py` — add same imports for `alembic upgrade head` on fresh DB
- `artifacts/ban_ke_hoach_v1/phase_03/phase_03_verdict.json` already PASS; `phase_04` already PASS — no Phase-5 overwrite

**Dirty preserved (not in Phase 5 agent scope):**
- `apps/desktop/native/recording-engine/*` Phase 3-5 recording-engine WGC/NVENC/libav dirty (Phase 5 there is `recording_engine_v2_phase_05` `BLOCKED` due to missing shared libav DLLs on this host — orthogonal to agent durability)
- `apps/api/windagent_api/composition/container.py`, `artifacts/ban_ke_hoach_v1/phase_02-04` as before

---

## 10. Invariants

- `one orchestration authority` kept — `OrchestratorService` remains entry point, `GoalService/CheckpointService/HeartbeatHardening` are narrow seams, not new orchestrators.
- `PostgreSQL durable authoritative` — goals/checkpoints live in `agent_*` tables; `_history` in memory only for test observation (never the durable source).
- `no worker-owned business state` preserved.
- `production composition cannot use memory fallback` — `DurableTaskLeaseManager._leases/_pending` in-memory is test-only fallback; production composes `DatabaseManager` + lease repository (gate `production composition cannot use memory fallback` still satisfied; `HeartbeatHardening` delegates to that lease).
- Trajectory correlation via `delegation_child_*` / `agent_checkpoint_*` / `persistent_goal_*` events through `MultiAgentRepository.append_event`.
- Checkpoints are opaque — never capture `credentials/provider/schedule/memory/promotion`.

**Next:** Phase 5 substrate feeds Milestone A exit → then Memory V2 + Evaluation V2 (Phase 6/7) toward `MILESTONE B — Evaluated Agent`.
