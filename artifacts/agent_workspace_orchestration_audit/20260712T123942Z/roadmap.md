# Gap Analysis + Roadmap (grouped)

Per-gap: current / expected / evidence / impact / dependency / difficulty S-M-L-XL /
order / acceptance test.

## Group 1 — Data model + migration
G1.1 Versioned migrations
- current: create_all only (database.py). No Alembic.
- expected: Alembic versioned migrations; rollback path.
- evidence: database.py init_models create_all; test_phase2 insert-only seed.
- impact: no upgrade/downgrade; prod unsafe.
- dep: none. diff: M. order: 1.
- acceptance: `alembic upgrade head` on fresh DB creates all tables; `downgrade` removes.

G1.2 Unique + FK on conversation keys
- current: parent_tasks.conversation_id / agent_instances.conversation_id loose string, no FK/index (models.py:371,464).
- expected: FK + index conversation_id; unique(windagent_session_id) on agent_sessions.
- evidence: models.py 371/464; sessions.py:117 scalar_one_or_none no unique.
- impact: MultipleResultsFound risk; slow joins.
- dep: G1.1. diff: S. order: 1a.
- acceptance: query AgentSessionORM by windagent_session_id returns 0/1 row enforced by DB.

G1.3 Immutable plan versions
- current: TaskPlanORM.version int counter, same row mutated (conversations.py patch).
- expected: new TaskPlanORM row per edit (snapshot) OR version-history table.
- evidence: conversations.py:243/288/322 plan.version bump; no row clone.
- impact: cannot audit plan history; weak req 12.
- dep: G1.1. diff: M. order: 1b.
- acceptance: editing plan while running creates new version row; old retrievable.

## Group 2 — Canonical model lock / same-model provider binding
G2.1 Acquire lock per turn
- current: session_bridge passes model="role:{router_role}" (131,208); no lock.
- expected: route_lock_service.acquire_lock(scope=conversation|parent_task|agent_session) before each run; persist routing_snapshot.
- evidence: session_bridge.py:131/208; route_lock_service exists unwired.
- impact: no 3-tier pin; no failover control.
- dep: G1.1. diff: M. order: 2.
- acceptance: run writes RouteLockORM + RouteAttemptORM; canonical id stable across retries.

G2.2 Same-model failover live
- current: unwired (Phase 1 integration gap).
- expected: on 429/5xx, select_binding same canonical; route attempt audited; cross-model forbidden (already enforced by acquire_lock invariant).
- evidence: route_lock_service.py:138-143,178-221,296-305; 0 live callers.
- impact: failover not exercised.
- dep: G2.1. diff: M. order: 2a.
- acceptance: inject 429 from provider A -> run continues on provider B, same canonical, RouteAttempt count=2, no cross-model.

G2.3 api_key plaintext (S1)
- current: models.py:269 store raw; column 163.
- expected: encrypt at rest; API never returns key.
- evidence: models.py:269/163; models.py:271 response no echo (good) but write plaintext.
- impact: secret leak.
- dep: none. diff: S. order: 2b (security, do early).
- acceptance: DB column ciphertext; GET /providers/{id} returns null api_key.

## Group 3 — Hermes multi-session supervisor
G3.1 Orchestrator spawns sub-agents
- current: supervisor.ensure_orchestrator + spawn_subagent exist, tests only.
- expected: one router endpoint (or chat tool) calls ensure_orchestrator then spawn_subagent per DAG node; maps AgentInstance+AgentRun+Hermes session.
- evidence: supervisor.py:54/79; 0 live callers.
- impact: no multi-agent.
- dep: G2.1. diff: L. order: 3.
- acceptance: POST spawn -> 2 sub-agents each independent run; events isolated by session_id.

G3.2 stop one sub-agent only
- current: supervisor.stop_subagent exists, called by cancel_task only.
- expected: stop selected sub-agent, siblings continue.
- evidence: supervisor.py:175-198.
- impact: granular control.
- dep: G3.1. diff: S. order: 3a.
- acceptance: stop agent B -> B cancelled, A/C keep streaming.

G3.3 reattach on boot
- current: supervisor.reattach defined, no startup caller.
- expected: main.py lifespan calls reattach after recover.
- evidence: supervisor.py:255-274; main.py:292 only recover.
- impact: in-memory map empty after restart.
- dep: G9. diff: S. order: 3b.
- acceptance: restart -> sub-agent runs re-populate supervisor map.

## Group 4 — DAG scheduler
G4.1 Wire run_plan
- current: dag_scheduler.run_plan real, tests pass, 0 callers.
- expected: orchestrator spawn -> run_plan executes nodes respecting edges.
- evidence: dag_scheduler.py:106-197; grep 0 live.
- impact: DAG inert.
- dep: G3.1. diff: L. order: 4.
- acceptance: A done -> B,C parallel -> D after both (fan-in gate holds).

G4.2 concurrency_group enforcement
- current: column exists, scheduler launches all ready (collision C3).
- expected: max 1 running run per concurrency_group / worktree.
- evidence: dag_scheduler run_plan; CODING_AGENT_TYPES single worktree.
- impact: worktree write collision.
- dep: G4.1, G5.1. diff: M. order: 4a.
- acceptance: two ready nodes same agent -> serialized, no cwd clash.

G4.3 retry without double side-effect (req 11)
- current: idempotency_key column, unused.
- expected: tool call writes idempotency_key; retry checks before re-exec.
- evidence: models.py:128; 0 writes.
- impact: duplicate side-effect.
- dep: G4.1. diff: M. order: 4b.
- acceptance: stream interrupt + retry -> tool runs once (idempotency_key dedup).

## Group 5 — Worktree isolation
G5.1 Live worktree per coding agent
- current: worktree_service real, wired to supervisor only (unwired live).
- expected: spawn_subagent(coding) creates worktree, sets workspace_root=cwd.
- evidence: worktree_service.py:74-102; supervisor.py:103-116.
- impact: coder writes main without isolation.
- dep: G3.1. diff: M. order: 5.
- acceptance: 2 coding agents -> 2 worktree paths; main untouched.

G5.2 Cleanup on cancel (C9)
- current: cancel_task stops sub-agent only, no worktree.remove.
- expected: cancel -> worktree_service.remove (quarantine+branch delete).
- evidence: conversations.py:523-527; worktree_service.remove:139-179.
- impact: orphan worktree+branch.
- dep: G5.1. diff: S. order: 5a.
- acceptance: cancel -> worktree dir gone, branch deleted.

G5.3 Worktree reconcile on boot
- current: recovery.recover no worktree reconcile.
- expected: recover scans orphan worktrees, removes dead, keeps live.
- evidence: recovery_service.py:78-110.
- impact: leaked worktrees after crash.
- dep: G9. diff: M. order: 5b.
- acceptance: restart with stale worktree -> cleaned or reattached.

## Group 6 — Durable events + recovery
G6.1 Conversation-level WS multiplex (req 15)
- current: /ws/{session_id} per-session; frontend N sockets.
- expected: /ws/{conversation_id} single socket; server fans out per agent_instance_id; envelope carries agent_instance_id.
- evidence: websocket.py:55; multiAgentStore.syncWebSockets:165-252.
- impact: req 15 unmet; connection sprawl.
- dep: none. diff: L. order: 6.
- acceptance: one socket receives events for all sub-agents tagged by agent_instance_id.

G6.2 Exponential backoff reconnect
- current: fixed 1500ms (multiAgentStore:218).
- expected: exponential backoff w/ cap + jitter.
- evidence: multiAgentStore:216-224.
- impact: thundering herd on mass disconnect.
- dep: G6.1. diff: S. order: 6a.
- acceptance: 10 forced disconnects -> intervals grow 1.5/3/6... capped.

G6.3 Partial stream audit (req 10, R6)
- current: save_partial_artifact exists, _stream_run 0 calls.
- expected: except branch calls save_partial_artifact (visibility=audit_only); transcript clean.
- evidence: partial_audit.py:17-41; session_bridge.py:430-438.
- impact: no audit trail on crash.
- dep: G4.1. diff: S. order: 6b.
- acceptance: kill stream mid-token -> PartialArtifactORM row audit_only; no assistant turn polluted.

G6.4 Full recovery rebuild (R9)
- current: runs+events only.
- expected: resume run_plan (scheduler rebuild), reconcile route locks, recover pending approvals.
- evidence: recovery_service.py:78-110.
- impact: state loss post-restart.
- dep: G4.1,G2.1. diff: L. order: 6c.
- acceptance: restart mid-DAG -> scheduler resumes from persisted node states; locks re-acquired; pending approvals surfaced.

## Group 7 — Frontend normalized multi-agent state
G7.1 Keep normalized store (already good)
- current: multiAgentStore agents/taskNodes/events[agentId] normalized.
- expected: same; add agent_instance_id tag on WS events for multiplex.
- evidence: multiAgentStore.tsx state shape.
- impact: OK; extend for G6.1.
- dep: G6.1. diff: S. order: 7.
- acceptance: events keyed by agent_instance_id; no cross-agent merge.

## Group 8 — UI 3 cols + task editor
G8.1 Labels i18n + Current Task compact
- current: English labels; Task Graph full.
- expected: Vietnamese labels per spec; Current Task compact variant.
- evidence: MultiAgentWorkspace:333/389/813.
- impact: cosmetic spec mismatch.
- dep: none. diff: S. order: 8.
- acceptance: column headers match spec strings.

G8.2 Browser live per-agent (R10)
- current: hardcoded Awesome App mock.
- expected: per-agent live preview or remove panel.
- evidence: MultiAgentWorkspace:899-1003.
- impact: req 18/20 violated.
- dep: G3.1. diff: M. order: 8a.
- acceptance: select agent A -> browser shows A session; B -> B session.

G8.3 Inspector full fields (R11)
- current: Status+Run only.
- expected: model/provider/task/permission/tool from AgentInstance.
- evidence: MultiAgentWorkspace:853-867.
- impact: req 19 partial.
- dep: G2.1,G3.1. diff: S. order: 8b.
- acceptance: inspector shows model+provider+permission of selected agent.

G8.4 Delete dead AgentWorkspace.tsx
- current: unmounted, has session-switching anti-pattern + chat-terminal.
- expected: delete.
- evidence: App.tsx:441 mounts MultiAgentWorkspace only.
- impact: confusion/dead debt.
- dep: none. diff: S. order: 8c.
- acceptance: grep AgentWorkspace import -> 0.

## Group 9 — E2E / chaos / security hardening
G9.1 Chaos: stop vs completion (C1)
- current: TOCTOU no row version.
- expected: AgentSessionORM version column; CAS update.
- evidence: session_bridge.py:283-292 vs 409-428.
- impact: status flip-flop.
- dep: G1.1. diff: S. order: 9.
- acceptance: concurrent stop+completion -> final status deterministic (cancelled wins if stop sent first).

G9.2 Chaos: orphan Hermes run (C8)
- current: reattached never cancelled.
- expected: recover cancels dead/orphan Hermes runs.
- evidence: recovery_service.py:93.
- impact: leaked processes.
- dep: G6.4. diff: M. order: 9a.
- acceptance: restart with live-but-abandoned run -> Hermes stop issued.

G9.3 SQLite WAL (C5)
- current: default journal.
- expected: PRAGMA journal_mode=WAL in database.py init.
- evidence: main.py:67; database.py.
- impact: lock under fan-out.
- dep: G1.1. diff: S. order: 9b.
- acceptance: 8 parallel agents write without "database is locked".

G9.4 Secret redaction (S2/R4)
- current: raw command in arguments_redacted.
- expected: scrub secrets before persist+emit.
- evidence: session_bridge.py:377.
- impact: secret exposure.
- dep: G2.2. diff: S. order: 9c.
- acceptance: command with token -> stored/displayed redacted.

G9.5 workspace_root traversal (S3/R5)
- current: unsanitized.
- expected: assert is_relative_to(repo_root).
- evidence: sessions.py payload -> bridge.
- impact: arbitrary dir agent.
- dep: none. diff: S. order: 9d.
- acceptance: payload workspace_root=../../etc -> 400 reject.

G9.6 Retry storm (C11)
- current: dag_scheduler retry no cap/jitter.
- expected: capped exponential backoff + max retries.
- evidence: dag_scheduler._run_task.
- impact: storm on persistent fail.
- dep: G4.1. diff: S. order: 9e.
- acceptance: agent always fails -> retry stops after N with backoff.

G9.7 E2E scenario coverage
- current: unit only; runtime unverified (services down).
- expected: TestClient E2E for scenarios 1-9 with fake Hermes.
- evidence: this audit Phase 5.
- impact: integration unproven.
- dep: all above. diff: L. order: 9f.
- acceptance: pytest E2E: orchestrator spawn -> DAG fan-in -> 429 failover -> restart recover -> WS reconnect no-dup.

## Difficulty tally
S: G1.2,G2.3,G3.2,G3.3,G5.2,G6.2,G6.3,G7.1,G8.1,G8.3,G8.4,G9.1,G9.3,G9.4,G9.5,G9.6
M: G1.1,G1.3,G2.1,G2.2,G4.2,G4.3,G5.1,G5.3,G6.4,G8.2,G9.2,G9.7
L: G3.1,G4.1,G6.1,G6.4
XL: R2 (wire orchestration end-to-end)

## Recommended order (top to bottom)
1 G1.1 migrations + G1.2 + G2.3 (security early) + G9.5 (traversal)
2 G2.1 + G2.2 lock/failover
3 G3.1 supervisor spawn + G3.2 + G3.3
4 G4.1 run_plan + G4.2 + G4.3 idempotency
5 G5.1 worktree + G5.2 + G5.3
6 G6.1 WS multiplex + G6.2 + G6.3 partial + G6.4 recovery
7 G7.1 normalized state
8 G8.1 labels + G8.2 browser + G8.3 inspector + G8.4 delete dead
9 G9.1-G9.7 chaos/security + E2E
