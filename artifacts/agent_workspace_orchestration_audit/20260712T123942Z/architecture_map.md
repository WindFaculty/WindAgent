# Architecture Map (real)

## Flow (live, Phase-1)
User -> Frontend (App.tsx tab "workspace" -> MultiAgentWorkspace)
  -> REST sessions.send_message POST /api/v1/sessions/{id}/messages
  -> session_bridge.submit_message
  -> HermesApiClient.start_run POST {base_url}/v1/runs
  -> _stream_run SSE GET /v1/runs/{run_id}/events
  -> HermesEventTranslator -> event_bus.publish -> WS /ws/{session_id}
  -> multiAgentStore / AgentBoardRow
SQLite windagent.db via db.database (create_all, no migrations).

## Flow (orchestration subsystems, UNWIRED)
Orchestrator chat NL
  -[MISSING]-> supervisor.ensure_orchestrator + spawn_subagent
  -[MISSING]-> dag_scheduler.run_plan
  -[MISSING]-> route_lock_service.acquire_lock
  -[MISSING]-> recovery.recover (boot only, partial)
  -[MISSING]-> partial_audit.save_partial_artifact (in stream crash)

## Components
- session_bridge.py: submit_message/submit_run/stop_run/_stream_run/_profile_decision/
  resolve_approval. Maps windagent_session_id -> AgentSessionORM (scalar_one_or_none).
- supervisor.py: ensure_orchestrator (creates AgentInstance agent_type=orchestrator),
  spawn_subagent (AgentInstance+AgentRun, worktree for coding, AgentSessionORM map),
  stop_subagent, reattach. NO live caller.
- dag_scheduler.py: run_plan, _run_task (retry/timeout), detect_cycle (3-color DFS),
  progress aggregation. NO live caller.
- route_lock_service.py: CanonicalModel/ProviderModelBinding, acquire_lock (enforces
  same canonical), select_binding, classify_error, should_switch_provider, cooldown.
  Instantiated main.py, NO live caller.
- worktree_service.py: create/list/remove (git worktree add -b), branch naming,
  integrate. Called by supervisor only (unwired).
- permission_profile.py: classify_command (Safe/Standard/Autonomous), per-call.
  Used by session_bridge._profile_decision (live). Default Standard.
- recovery_service.py: seed_seq, replay_after, recover (runs+events only).
- event_bus.py: publish persist-then-broadcast, per-session asyncio.Queue maxsize 256,
  drop on full (recoverable via seq replay).
- websocket.py: /ws/{session_id} per-session; ?after_seq replay; control pause/resume/
  stop/permission.
- conversations.py: task graph CRUD, edit optimistic lock (plan.version 409), cycle
  detect, pause/resume/cancel/retry (flag nodes only), replan_notification.

## Danger points
- session_bridge assumes 1 AgentSession per windagent session (scalar_one_or_none).
- spawn_subagent / run_plan / acquire_lock / save_partial_artifact: 0 live callers.
- start_run passes model="role:{router_role}" string, not canonical locked id.
- WS per-session, not conversation-multiplexed.
- recovery rebuilds runs+events, not scheduler/lock/worktree/approval.
