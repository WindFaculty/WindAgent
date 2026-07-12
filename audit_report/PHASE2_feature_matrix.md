# PHASE 2 — Feature matrix

Status legend: IMPLEMENTED / PARTIAL / STUB_OR_MOCK / ABSENT / BROKEN / UNVERIFIED_RUNTIME
All 33 phase2-9 backend tests PASS (pytest, 6.4s). No live services running
(backend:8765 DOWN, frontend:1420 DOWN) => every "real Hermes integration"
claim is UNVERIFIED_RUNTIME; only the contract/unit harness is proven.

## A. ORCHESTRATOR
Status: PARTIAL
- Evidence: supervisor.ensure_orchestrator creates AgentInstance agent_type=
  "orchestrator" (supervisor.py:54-77). Frontend column 1 = "Orchestrator Chat"
  always talks to one conversation session (MultiAgentWorkspace.tsx:333-387,
  useOrchestratorChat:20-102 -> sendMessage(conversationId)).
- MISSING: no orchestrator tool schema to create parent task / DAG. spawn_subagent
  + ParentTaskORM/TaskPlanORM construction appear ONLY in tests. Task creation is
  manual via UI editor (createTaskNode REST), NOT model-driven structured tool
  calls. No artifact aggregation of sub-agent results in any live path.
- Severity: HIGH. Confidence: 0.85

## B. MULTI-AGENT SESSION MODEL
Status: PARTIAL
- Schema supports N: AgentInstanceORM (conversation_id, no unique) + AgentRunORM
  (FK agent_instance_id) — 1 conversation:N instances:N runs (models.py:464-494).
  supervisor.spawn_subagent persists both (supervisor.py:79-173).
- DANGER (confirmed): session_bridge maps by windagent_session_id with
  scalar_one_or_none (submit_message:117-121, stop_run:258-263) — assumes ONE
  AgentSession per windagent session. Sub-agent path (submit_run) deliberately
  bypasses AgentSessionORM, but the legacy single-agent path still enforces 1:1.
- stop: stop_subagent(run_id) stops one run/instance (supervisor.py:175-198) —
  correct granularity. But this is only reachable via task cancel, not wired to
  a live spawn flow.
- Severity: MEDIUM. Confidence: 0.80

## C. TASK DAG
Status: PARTIAL (engine IMPLEMENTED, not wired)
- Real DAG: TaskNodeORM + TaskEdgeORM + TaskPlanORM (models.py:406-444).
  dag_scheduler.py: 3-color DFS cycle detection (detect_cycle:36-69), dependency
  resolution (_deps_done_by:199-210), parallel launch via asyncio (run_plan:106-197),
  retry+timeout (_run_task:212-283), fan-in gate (waits all upstream completed),
  progress aggregation (285-301). This is a genuine DAG, not order_index.
- test_phase5 proves fan-out/fan-in + retry pass.
- MISSING: run_plan has NO live caller. No scheduler.run_plan invocation from any
  router; parent task/plan never created outside tests. concurrency_group column
  exists but scheduler does not enforce concurrency-group limits (launches all ready).
- Severity: HIGH. Confidence: 0.85

## D. TASK EDITING
Status: IMPLEMENTED (edit surface), PARTIAL (live-run editing)
- conversations.py: create/delete node (277-352), create/delete edge (355-444),
  patch node (232-274). Optimistic locking via plan.version 409 conflict. Cycle
  detection on edge add (394-399). replan_notification event emitted. UI editor
  present (Edit Plan mode, handleAddNode/Edge:133-234).
- pause/resume/cancel/retry endpoints (447-557); cancel wires supervisor.stop_subagent.
- PARTIAL: version = single counter on same plan row, NOT immutable versioned
  snapshots. No live scheduler to coordinate editing a running DAG.
- Severity: MEDIUM. Confidence: 0.80

## E. MODEL PINNING (3 tiers)
Status: PARTIAL
- RouteLockORM.scope_type accepts conversation|parent_task|agent_session
  (models.py:327). AgentInstanceORM has route_lock_id + selected_provider_binding_id.
- MISSING: no live code acquires a lock per turn. session_bridge.start_run passes
  model=f"role:{router_role}" (131,208) — a role string, not a canonical id via a
  lock. Resolution frequency UNVERIFIED_RUNTIME (no live path resolves).
- Severity: HIGH. Confidence: 0.80

## F. SAME-MODEL PROVIDER FAILOVER
Status: IMPLEMENTED (logic), ABSENT (in live path)
- Canonical/provider split (models.py:282-318). acquire_lock ENFORCES invariant:
  raises on different canonical model (route_lock_service.py:138-143) => cross-model
  fallback structurally forbidden within a lock. select_binding same-canonical only
  (178-221). Error taxonomy classify_error (51-78), should_switch_provider (296-305),
  5xx retry-same (308-310), cooldown (275-285), auth-disable (287-293), route_attempts
  audited. test_phase3 passes.
- CRITICAL CAVEAT: not on production path. session_bridge hands a role string to
  remote Hermes; failover never exercised by real requests. Cross-model-in-locked-
  session claim UNVERIFIED_RUNTIME (guard exists, unwired).
- Severity: HIGH (unwired). Confidence: 0.80

