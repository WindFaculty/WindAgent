# PHASE 5 — Runtime / black-box verification

Service state at audit time:
- backend :8765 = DOWN (curl connection refused)
- frontend :1420 = DOWN
No dev server started (task forbids long-lived dev server). Existing pytest /
TestClient harness used. Per rules, all real-Hermes scenarios = UNVERIFIED_RUNTIME.
Fake-Hermes / unit evidence and real-Hermes evidence are separated below.

Fake/contract + unit evidence (proven): 33 phase tests pass, incl. supervisor
spawn (fake bridge), DAG fan-out/fan-in, route-lock failover logic, recovery.
Real Hermes evidence: NONE (no server running; session_bridge talks to a remote
Hermes REST server that is not up).

SCENARIO 1 — Basic Hermes run: UNVERIFIED_RUNTIME.
  Code path exists (sessions.send_message -> submit_message -> start_run ->
  _stream_run -> stop_run sets status cancelled, emits user_stopped). Not executed
  live. stop-run unit behavior covered by baseline commit + test_websocket.

SCENARIO 2 — Multi-agent same conversation: UNVERIFIED_RUNTIME + PARTIAL by design.
  test_phase4 proves supervisor spawns >=3 independent instances/runs with a fake
  bridge (test_phase4_supervisor.py:128-133). BUT no live orchestrator invokes
  spawn_subagent, and WS is per-session not per-conversation, so real event-mixing
  behavior is unproven. Event isolation depends on distinct session_id buses.

SCENARIO 3 — DAG fan-out/fan-in (A done -> B,C parallel -> D): IMPLEMENTED + unit-
  PROVEN (test_phase5_dag_scheduler.py:82,114 via run_plan). NOT wired to live spawn.

SCENARIO 4 — 429 same-model failover: logic IMPLEMENTED + unit-PROVEN (test_phase3);
  live occurrence UNVERIFIED_RUNTIME and UNWIRED. Cross-model fallback structurally
  blocked by acquire_lock invariant, but the invariant is not enforced on the live
  start_run path (which uses role strings, not locks).

SCENARIO 5 — Interrupted stream partial audit-only / clean transcript:
  PARTIAL/BROKEN. PartialArtifactORM + save_partial_artifact exist and default
  audit_only, but session_bridge._stream_run does NOT persist partial output on
  crash (0 calls). So "partial kept for audit, hidden from transcript" is NOT true
  in the live path — partial text is simply dropped and a generic error event emits.

# EXECUTIVE SUMMARY

Overall: The Agent Workspace Orchestration is a well-engineered set of STANDALONE,
UNIT-TESTED subsystems (DAG scheduler, route-lock failover, worktree isolation,
permission profiles, durable replay, recovery) plus a real 3-column frontend with
genuine DAG rendering, real per-agent terminal streaming, task editing with
optimistic locking + cycle detection, and per-agent WebSocket reconnect/replay.

BUT the orchestration core is NOT INTEGRATED into the live request path. The
production flow is still the Phase-1 single-agent bridge: chat -> start_run(role
string) -> SSE stream. The orchestrator does not create parent tasks/DAGs via tool
calls, does not spawn sub-agents, does not acquire route locks, does not run the DAG
scheduler, and does not persist partial streams. These capabilities live only in
services + tests.

Provenance: everything is UNCOMMITTED working-tree state on top of baseline 9205dfa.
HEAD == ref, diff empty.

Top severities:
- HIGH: orchestrator DAG/spawn not wired (A,C); model pinning + failover not on live
  path (E,F); partial-stream audit not persisted live (G); WS per-session not
  conversation-multiplexed + fixed backoff (J); recovery does not rebuild scheduler/
  locks/worktrees/approvals (K); all feature work uncommitted (provenance).
- MEDIUM: 1:1 session assumption via scalar_one_or_none (B); browser preview
  hardcoded mock (L, violates req 20); inspector missing model/provider/task (L);
  no versioned migrations, missing FK/unique/index (Phase 3); secret redaction
  column unused (I); pending-approval recovery absent (I/K).

Requirement verdicts (condensed):
1 orchestrator-only chat: PARTIAL. 2 parent+DAG via NL: ABSENT (live) / PARTIAL.
3 independent sub-agent sessions: PARTIAL (schema+service, unwired). 4 parallel/dep/
fan-in: IMPLEMENTED (engine), unwired. 5 coder worktree: IMPLEMENTED (service),
unwired. 6 research no worktree: IMPLEMENTED. 7 3-tier pin: PARTIAL (schema only).
8 router keeps canonical: IMPLEMENTED (logic), unwired. 9 429 same-model failover:
IMPLEMENTED (logic), unwired. 10 partial audit-hidden: PARTIAL/BROKEN live.
11 idempotency: PARTIAL (column only). 12 editable/versioned/cycle-checked plan:
IMPLEMENTED (edit+cycle), PARTIAL (versioning). 13 default Standard: IMPLEMENTED.
14 restart recovery of conv/task/agent/lock/events: PARTIAL (runs+events only).
15 conversation-level multiplexed WS: ABSENT (per-session). 16 seq/reconnect/replay:
PARTIAL (seq+replay yes; exponential backoff no; drop-recovery no). 17 3 columns:
IMPLEMENTED (English labels). 18 terminal+browser per selected sub-agent: PARTIAL
(terminal real, browser hardcoded mock). 19 inspector state/model/provider/task/
tool/permission: PARTIAL (status+run only). 20 no mock/hardcoded: BROKEN (browser
preview + App.tsx metrics fallback are mock; terminal is real).

Files: audit_report/AUDIT_agent_workspace_orchestration.md (Phase 0-1),
PHASE2_feature_matrix.md (A-F), PHASE2_feature_matrix_G_L.md (G-L),
PHASE3_4_schema_tests.md, PHASE5_summary.md (this).
