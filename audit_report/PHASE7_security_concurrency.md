# PHASE 7 — Security + Concurrency audit

Services DOWN. Static + unit only. Some runtime races NOT verifiable (marked).

## SECURITY

### S1 API key returned / stored plaintext — HIGH
- models.py:269 `provider.api_key = payload.api_key` (POST /v1/providers/{id} PATCH).
  Raw key stored in model_providers.api_key (models.py:163). Response at
  models.py:271 does NOT echo key back, but DB stores plaintext. No encryption,
  no redaction. GET /v1/models seeds seed's via api_key_env (env var, safe), but
  direct provider update persists literal key. Any DB read / future GET leaks it.
- Fix path: store in secret store or encrypt-at-rest; never return.

### S2 PermissionRequest stores raw command, not redacted — MEDIUM
- session_bridge.py:377 `arguments_redacted=str(event.get("command") or "")`.
  Column named arguments_redacted but holds RAW command string (incl. secrets
  that may be in command). Redaction never applied. DB + UI show raw
  (MultiAgentWorkspace permission popup prints command verbatim:1038-1056).
- Violates req "secret redaction". Fix: actually scrub secrets from command
  before persist/emit.

### S3 Path traversal via workspace_root — MEDIUM
- sessions.create_session accepts payload.workspace_root (sessions.py:42-59);
  flows to AgentSessionORM.workspace_root + bridge.create_session(workspace_root=...)
  (session_bridge.py:152,166). NO os.path.resolve/is_relative_to check anywhere.
  Attacker supplies "../../etc" → bridge runs Hermes against arbitrary dir.
- worktree path uses repo_root + fixed segments (worktree_service.py:60-64) —
  no user path injected there, safe. But session workspace_root is unsanitized.

### S4 Permission bypass — LOW (profile enforced per-call)
- classify_command consulted per approval.request (session_bridge.py:296-320).
  Autonomous auto-allows; Safe auto-denies risky; Standard needs approval.
  Bypass risk: if Hermes emits approval.request WITHOUT command field →
  _profile_decision returns "pending" (line 304-305), user must approve blind.
  Acceptable. No silent allow.

### S5 Command injection — LOW
- classify_command only inspects string; never shells out. Injection risk lives
  in Hermes runtime, not this module. Not in scope of code audited.

## CONCURRENCY

### C1 Stop vs completion race — MEDIUM (TOCTOU)
- stop_run sets status="cancelled" (session_bridge.py:283-292). _stream_run
  completion branch (409-428) sets completed/cancelled/failed with NO guard
  that stop already ran. If Hermes emits run.completed after local stop set
  cancelled, completion branch overwrites to "completed". No row version / CAS.
- Not verifiable runtime. Likely under concurrent stop+finish.

### C2 Two events same sequence — LOW (mitigated)
- event_bus assigns seq via single-threaded coroutine per publish (event_bus.py:
  66-75). asyncio single event loop => no two publishes interleave seq increment.
  DB event_seq nullable, no unique(session_id,seq). Replay dedup relies on client
  compare (multiAgentStore:127). If two events somehow same seq, client keeps
  higher-only. Low.

### C3 Two tasks assigned same agent — MEDIUM
- dag_scheduler launches all ready tasks (no concurrency_group enforcement,
  dag_scheduler.py run_plan). If two nodes assigned same agent_instance_id and
  both ready, scheduler runs both concurrently against same AgentInstance/
  worktree (race on AgentRunORM insert + worktree cwd). concurrency_group column
  exists, unused. Schema allows N AgentRuns per instance (intended fan-out) but
  cwd/worktree single => two runs write same worktree = collision. Not verifiable.

### C4 Two runs update AgentSessionORM — LOW
- session_bridge maps 1:1 windagent_session_id (scalar_one_or_none:263). Sub-agent
  path bypasses AgentSessionORM, uses AgentRunORM per run_id. Different runs =
  different AgentRun rows. Low. But scalar_one_or_none assumption unsafe if future
  spawns >1 AgentSession per windagent session (Phase 3 danger #1).

### C5 SQLite lock — MEDIUM (unverifiable)
- DB_URL from env (main.py:67), default sqlite. No WAL/journal_mode set in
  database.py init. Parallel fan-out N Hermes loops + event hooks all write one
  DB. SQLite single-writer => "database is locked" under load. Not verified runtime.

### C6 Unbounded queue — LOW (bounded)
- event_bus subscriber queue maxsize=256 (event_bus.py:97). Bounded. Full => drop
  (recoverable via seq replay). Not unbounded.

### C7 Dropped WS event — LOW (recoverable)
- Drop on full queue; event already persisted => replay_after recovers (Phase 6
  Scenario 6). No permanent loss. OK by design.

### C8 Orphan Hermes task after restart — MEDIUM
- recovery.recover(): dead run -> interrupted (recovery_service.py:96). But if
  Hermes run still alive (status running) -> reattached, NO cancel issued. A run
  cancelled in backend but not via stop_run leaves live Hermes run = orphan.
  Also recovery never calls stop on dead runs. Orphan persists.

### C9 Orphan worktree / branch — MEDIUM
- recovery.recover() does NOT reconcile worktrees or branches. Cancel path
  (conversations.cancel_task:523-527) calls supervisor.stop_subagent only; does
  NOT call worktree_service.remove. Worktree + branch windagent/... left on disk
  forever after cancel. test_phase6 removes explicitly but live cancel leaks.
- No cleanup-after-cancellation wired.

### C10 Stale provider cooldown — NOT VERIFIABLE
- route_lock_service cooldown logic exists (275-285) but unwired on live path
  (Phase 1). No live cooldown runs => cannot assess staleness.

### C11 Retry storm — MEDIUM
- route_lock should_switch_provider + retry_same_provider (5xx:308-310) but
  unwired. dag_scheduler _run_task retries on failure (retry_count) with fixed
  delay, no backoff cap, no jitter => potential storm if agent keeps failing.
  Unwired live, but logic gap in scheduler. Not verifiable.

## Severity tally
HIGH: S1 (api_key plaintext).
MEDIUM: S2, S3, C1, C3, C5, C8, C9, C11.
LOW: S4, S5, C2, C4, C6, C7.
NOT VERIFIABLE: C5, C10, C11 (runtime), C1/C3 (race timing).
