
## PHASE 1 — Architecture map (real)

User
 -> Frontend (apps/desktop): App.tsx tab "workspace" -> MultiAgentProvider +
    MultiAgentWorkspace.tsx. Conversation id = sessionStorage uuid.
 -> REST: sessions.send_message POST /api/v1/sessions/{id}/messages;
    conversations.py task-graph + task-edit endpoints; worktrees.py; events.py.
 -> WebSocket: /ws/{session_id} (websocket.py) — PER SESSION, not per conversation.
 -> Session bridge (services/hermes/session_bridge.py): submit_message/submit_run
    -> HermesApiClient.start_run -> POST {base_url}/v1/runs; _stream_run consumes
    SSE GET /v1/runs/{run_id}/events, translates, publishes to event_bus.
 -> Router/model: route_lock_service.py (canonical pin + same-model failover),
    model_service, canonical_models/provider_model_bindings tables.
 -> Event bus (event_bus.py): publish hooks persist ExecutionEventORM (+ JSONL).
 -> SQLite: windagent.db via db/database.py (create_all, no versioned migrations).

Key wiring fact (main.py lifespan): route_lock_service, dag_scheduler,
hermes_supervisor, worktree_service, recovery_manager are ALL instantiated and
attached to app.state, and recovery_manager.recover() runs on boot.

## PHASE 1 — Integration gap (decisive, evidence-based)

grep across apps/backend for the orchestration entry points, EXCLUDING tests:
- spawn_subagent : callers = supervisor.py (def) + test_phase4 ONLY
- ensure_orchestrator : def + test_phase4 ONLY
- run_plan (DAGScheduler): def + test_phase5 ONLY
- ParentTaskORM(...) / TaskPlanORM(...) constructed: tests ONLY
- RouteLockService / select_binding / acquire_lock / should_switch_provider:
  main.py (instantiation) + test_phase3 ONLY — NOT referenced in session_bridge
- save_partial_artifact / PartialArtifact in session_bridge.py: 0 occurrences

=> The live chat path (sessions.send_message -> bridge.submit_message ->
   client.start_run) NEVER calls the supervisor, the DAG scheduler, the route
   lock service, or the partial-audit writer. These subsystems exist as
   well-tested standalone libraries but are NOT on any production request path.
   No router imports spawn_subagent/run_plan/acquire_lock (verified: 0 matches
   in apps/backend/routers for those patterns).
