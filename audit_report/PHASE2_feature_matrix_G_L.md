# PHASE 2 — Feature matrix (G–L)

## G. PARTIAL STREAM + IDEMPOTENCY
Status: PARTIAL
- PartialArtifactORM (models.py:517-530) visibility="audit_only" default.
  partial_audit.save_partial_artifact writes audit_only (partial_audit.py:17-41).
  route_lock classify_error distinguishes STREAM_INTERRUPTED vs TIMEOUT_BEFORE_TOKEN.
- ToolCallORM.idempotency_key column exists (models.py:128) with comment.
- MISSING/BROKEN CLAIMS:
  * session_bridge._stream_run does NOT call save_partial_artifact on stream crash
    (grep count = 0). On exception it emits a generic "error" event
    (session_bridge.py:430-438); partial text is NOT persisted in the live path.
  * No "interrupted" turn state applied to messages; no dedup/suppression logic
    keying on idempotency_key anywhere in live code (only column defined).
  * Whether retry re-runs a tool twice: UNVERIFIED — idempotency_key is never
    written or checked by any executor in the live path.
- Req 11 idempotency (retry no double tool-run): PARTIAL/BROKEN. idempotency_key
  column exists (models.py:128) but grep = 0 writes/reads anywhere in live code.
  No dedup, no suppression, no guard. route_lock retry_same_provider (5xx) is
  REQUEST retry to provider, not tool-call idempotency, and unwired. Whether retry
  after stream-interrupt runs a tool twice = UNVERIFIED_RUNTIME, leans BROKEN (no
  key written/checked live). Severity HIGH. Confidence 0.80.
- Severity: HIGH. Confidence: 0.75

## H. WORKTREE ISOLATION
Status: IMPLEMENTED (service), PARTIAL (wiring)
- worktree_service.py: create (git worktree add -b, coding-agent-only via
  CODING_AGENT_TYPES:38-40), branch naming windagent/<conv>/<task>/<inst>
  (66-70), per-agent cwd = worktree path, _assert_git_repo guard, idempotent reuse
  (94-102), remove with quarantine (139-179), capture_diff incl untracked
  (181-213), integrate merge/cherry-pick with --merge --abort on conflict
  (224-296). WorktreeORM persisted (models.py:499-512). test_phase6 passes.
- supervisor.spawn_subagent calls worktree.create for coding agents and sets
  workspace_root to worktree path (supervisor.py:103-116) — but spawn_subagent
  itself is unwired (see A/C).
- Research/Browser/Orchestrator get None (create returns None for non-coding) —
  matches requirement 6.
- Path-traversal validation: relies on fixed repo-root join; no explicit
  out-of-workspace command block beyond permission_profile patterns.
- Severity: MEDIUM (unwired live). Confidence: 0.80

## I. PERMISSION PROFILE
Status: IMPLEMENTED
- permission_profile.py: Safe/Standard/Autonomous (28), default Standard, fail-safe
  to Standard on unknown (74). Per-command classification (classify_command:69-92),
  install/push/pr/merge/rm-rf/reset--hard/drop patterns (_APPROVE_PATTERNS:31-47),
  hard-blocked force-push/mkfs/chmod-777-root (_BLOCKED_PATTERNS:51-56).
- Applied per tool call in live approval path: session_bridge._profile_decision
  looks up AgentInstance.permission_profile and classifies command
  (session_bridge.py:296-320); _stream_run auto-grants/denies/pends accordingly
  (386-392). AgentInstanceORM.permission_profile default "Standard" (models.py:473).
- Persistence: PermissionRequestORM persisted (663-676); resolve_approval updates
  status (322-349). Restart recovery of pending approvals: NOT handled by
  recovery_service.recover (only runs, not approvals) — GAP.
- secret redaction: arguments_redacted column exists but _stream_run stores raw
  command string (377) — redaction NOT actually applied. GAP.
- Severity: MEDIUM. Confidence: 0.80

## J. DURABLE EVENTS + WEBSOCKET
Status: PARTIAL
- Events persisted via event_bus publisher hook (make_execution_event_hook) BEFORE
  broadcast; ExecutionEventORM has event_seq (models.py:145). replay_after +
  seed_seq (recovery_service.py:42-74). WS replay on reconnect via ?after_seq
  (websocket.py:75-88). Client dedup by seq (multiAgentStore.appendEvents:123-140).
  Reconnect w/ 1500ms delay (multiAgentStore:216-224).
- CRITICAL GAPS vs requirements 15/16:
  * WebSocket is PER-SESSION (/ws/{session_id}, websocket.py:55), NOT one
    conversation-level socket multiplexing all sub-agents. Frontend opens N sockets,
    one per sub-agent session_id (multiAgentStore.syncWebSockets:165-252). Req 15
    ("WebSocket cap conversation, multiplex mọi sub-agent") = NOT met.
  * sequence is per-session (ExecutionEventORM.session_id scope), not per-conversation.
  * Reconnect backoff is FIXED 1500ms, not exponential (req 16). 
  * No queue-full drop policy / dropped-event recovery beyond seq replay.
- Severity: HIGH. Confidence: 0.80

## K. RESTART RECOVERY
Status: PARTIAL
- main.py lifespan calls recovery_manager.recover() on boot (main.py:292-295).
  recover() scans AgentRun status=running, checks Hermes get_run, marks dead runs
  interrupted + task retryable (recovery_service.py:78-110). Conservative (never
  auto-completes). supervisor.reattach repopulates in-memory maps (supervisor.py:255-274).
- GAPS: scheduler DAG NOT rebuilt on boot (no run_plan resume). route locks NOT
  reconciled on boot (no call). worktrees NOT reconciled on boot. pending approvals
  NOT recovered. reattach() has no live caller in main.py startup (only defined).
  Frontend reload re-fetches via polling + after_seq replay (multiAgentStore) — OK.
- Severity: HIGH. Confidence: 0.78

## L. FRONTEND UX
Status: PARTIAL
- 3 columns present: col1 "Orchestrator Chat" (333-387), col2 "Sub-agent Board" +
  "Task Graph" (389-...), col3 "Agent Inspector" (813). Matches req 17 layout but
  labels are English ("Orchestrator Chat"/"Sub-agent Board"/"Task Graph"/"Inspector"),
  not the Vietnamese "Agent Điều Phối / Sub-agents / Current Task thu nhỏ".
- Task Graph shows REAL DAG (taskNodes/taskEdges from REST, getPrerequisites traces
  edges:321-328) — not tool calls. Good.
- Sub-agent card: shows agent_type, permission_profile, status (428-437). MISSING
  model, provider, worktree, task on the card.
- Terminal: REAL — streams terminal_output events per selected agent
  (multiAgentStore:202-205, termLines:280, render:887-897). Not split from chat. Good.
- Browser/App Preview: HARDCODED MOCK "Awesome App" (899-1003) — static markup,
  not per-sub-agent browser session. Violates req 18 + req 20 (no mock).
- Inspector: switches with selected agent (selected:276-278) but only shows
  Status + Run (853-867); NO model/provider/task/permission/tool panel. Req 19 PARTIAL.
- Multiple simultaneous assistant streams: orchestrator chat is single conversation
  socket; per-agent terminals separate — mixing avoided for terminals. Chat delta
  appends to last assistant bubble (60-74) — could interleave if concurrent.
- Severity: MEDIUM. Confidence: 0.80
