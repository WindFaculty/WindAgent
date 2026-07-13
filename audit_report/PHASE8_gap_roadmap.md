# PHASE 8 — Gap analysis + roadmap (caveman)

## PERSISTENCE gaps
- All feature code UNCOMMITTED on top of baseline 9205dfa. Commit before anything else. (Critical, process)
- No versioned migration. create_all only. Add Alembic. (High)

## UI claim checks (this session)
- Edit/Retry/Pause/Resume backend contract: EXISTS (conversations.py:447-557,
  client.ts:406-419 match). Claim FALSE. But executor (DAG scheduler) unwired =>
  buttons flag TaskNode status, no live effect. (Medium)
- Status card hardcoded: FALSE. Card reads a.status/a.run_status/a.agent_type from
  DB (MultiAgentWorkspace:429-437,857-864). Only chat header "Active" badge
  static (line 342). (Low)
- Agent selector switches session: FALSE on live (MultiAgentWorkspace select()).
  TRUE only in dead AgentWorkspace.tsx (unmounted) where dropdown=agent_type =>
  createSession. Delete dead file. (Low/Medium debt)

## ARCHITECTURE gaps (from Phase 1-7)
- Orchestrator tool-schema DAG spawn: ABSENT live. supervisor.spawn_subagent +
  run_plan + ParentTaskORM construction = tests only. (High)
- Model pin 3-tier + same-model failover: logic exists, unwired. session_bridge
  passes role string to remote Hermes (session_bridge.py:131,208). (High)
- Partial stream audit: column + service exist, NOT called in live stream. (High)
- WS conversation-multiplex: ABSENT. Per-session socket, fixed 1500ms backoff. (High)
- Recovery rebuild: runs+events only. No scheduler/lock/worktree/approval rebuild. (High)
- Browser preview: MOCK hardcoded. Violates req 18+20. (Medium)
- Inspector: status+run only. No model/provider/task/permission/tool. (Medium)

## SECURITY gaps
- S1 api_key plaintext store. (High)
- S2 raw command in "arguments_redacted". (Medium)
- S3 workspace_root path traversal unsanitized. (Medium)

## CONCURRENCY gaps
- C1 stop/completion TOCTOU, no row version. (Medium)
- C3 two tasks same agent + single worktree cwd = collision. (Medium)
- C5 SQLite no WAL under fan-out. (Medium)
- C8 orphan Hermes run (reattached, never cancelled). (Medium)
- C9 orphan worktree+branch after cancel (no remove call). (Medium)

## ROADMAP (priority order)
1. Commit feature worktree. Alembic migrations. (process/High)
2. Wire orchestrator: chat -> spawn_subagent -> run_plan. One router path.
   (High, unblocks A/C/D/E/F/G/J/K at once)
3. session_bridge: acquire route_lock per turn; persist routing snapshot;
   call save_partial_artifact on stream crash; write idempotency_key + dedup.
   (High)
4. WS: one /ws/{conversation_id} multiplexing agent sessions; exponential
   backoff; per-conversation seq. (High)
5. recovery.recover: rebuild scheduler (resume run_plan), reconcile route locks,
   worktree reconcile, cancel dead Hermes runs, recover pending approvals. (High)
6. Security: encrypt/never-return api_key; scrub secrets in command;
   validate workspace_root (is_relative_to repo root). (High/Medium)
7. Browser preview: replace mock with per-agent live session (real or hide). (Medium)
8. Inspector: add model/provider/task/permission/tool panel from AgentInstance. (Medium)
9. Concurrency: row version on AgentSessionORM for stop/complete; enforce
   concurrency_group; SQLite WAL; cancel => worktree.remove + Hermes stop. (Medium)
10. Delete dead AgentWorkspace.tsx. (Low)

## VERDICT
Feature = mature standalone libraries + 3-column UI shell. Live path still
Phase-1 single-agent. Orchestration unwired = biggest gap. Security has real
HIGH (plaintext key). No runtime verified (services down). 33/33 unit pass
prove modules, not integration.
