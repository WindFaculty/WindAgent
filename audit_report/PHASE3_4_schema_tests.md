# PHASE 3 — Database schema

DB: SQLite (sqlite+aiosqlite:///./windagent.db). Init: db.init_models() =>
Base.metadata.create_all. NO Alembic / versioned migrations. seed_canonical_models
+ test_phase2_migration is a non-destructive insert helper, NOT production migration.
=> create_all is NOT production-ready migration (req: do not treat create_all as such).

Tables mapped to requirements (models.py):
- conversation/session: chat_sessions (35), agent_sessions (642), agent_instances (464)
- message: messages (53)
- workflow / workflow step: workflows (72), workflow_steps (93) [legacy linear path]
- parent task: parent_tasks (371) PK id, conversation_id (NO FK, NO unique)
- task plan: task_plans (390) FK parent_task_id
- task node: task_nodes (406) FK plan_id
- task edge: task_edges (431) FK plan_id, from/to FK task_nodes
- task artifact: task_artifacts (447) FK task_nodes
- agent instance: agent_instances (464) — conversation_id NO FK
- agent run: agent_runs (480) FK agent_instance_id
- canonical model: canonical_models (282)
- provider binding: provider_model_bindings (300) FK canonical
- route lock: route_locks (323) FK canonical
- route attempt: route_attempts (345) FK route_lock, surrogate int PK
- event sequence: execution_events (137) event_seq nullable
- permission: permission_requests (663)
- worktree: worktrees (499)

DANGEROUS ASSUMPTIONS (confirmed):
1. session_bridge queries AgentSessionORM by windagent_session_id with
   scalar_one_or_none (submit_message:117, stop_run:259) — NO unique constraint on
   windagent_session_id, but code assumes uniqueness. With future N-agents-per-session
   this can raise MultipleResultsFound. HIGH.
2. parent_tasks.conversation_id / agent_instances.conversation_id have NO FK and NO
   index — conversation is a loose string key across tables. MEDIUM.
3. conversations.task_graph queries ParentTaskORM by conversation_id with .first()
   (conversations.py:68-72) — silently picks one parent task if multiple exist.
   No uniqueness guarantee (one conversation could have >1 parent task). MEDIUM.
4. execution_events.event_seq is NULLABLE with no per-session UNIQUE(session_id,seq)
   constraint — dedup relies on client seq compare; DB does not enforce monotonicity
   or uniqueness. Replay correctness depends on the publisher hook. MEDIUM.
5. Cascade: chat_sessions -> messages/workflows cascade all,delete-orphan (OK).
   parent_tasks -> plans cascade; route_locks -> attempts cascade. BUT task_nodes/
   task_edges/task_artifacts have FK to plan/nodes with NO cascade config => orphan
   rows possible on plan delete. MEDIUM.
6. SQLite single-writer: multiple concurrent agent runs + event hooks all write to
   one windagent.db. No WAL/config verified. Write contention risk under real
   parallel fan-out. MEDIUM — UNVERIFIED_RUNTIME.

# PHASE 4 — Tests

Official command (pyproject.toml present). Ran with .venv python:
  pytest tests/test_phase2..9 -q
Result: 33 passed, 1 warning, 6.41s, exit 0.
- start: 2026-07-12; single suite; no parallelism (avoided SQLite lock).
- Covers: migration/seed, route lock + failover logic, supervisor spawn (with fake),
  DAG scheduler fan-out/fan-in/retry, worktree+permission, durable recovery,
  conversations API, task editing.
- Did NOT run: full backend suite (many phase1 tests + GUI), frontend vitest
  (not executed — no live requirement, time). Marked UNVERIFIED for those.
- No code modified to pass tests.

These tests validate the STANDALONE modules. They do NOT prove the modules are
invoked by the live request path (see Phase 1 integration gap).
