# PHASE 5 (cont) — Scenarios 6-9 + PHASE 6 UI/backend delta

Services DOWN (:8765, :1420). All real-Hermes = UNVERIFIED_RUNTIME.
Static + unit only. No temp sim code created in source tree.

## SCENARIO 6 — WS reconnect + replay: IMPLEMENTED (design), UNVERIFIED_RUNTIME
- event_bus.publish persist-then-broadcast (event_bus.py:58-95): DB hook BEFORE
  fan-out => subscriber never sees unpersisted event.
- Drop policy: subscriber queue maxsize=256; QueueFull => drop, "client replays via
  seq" (92-93). Dropped event still in DB => replay_after recovers it. No data loss.
- Reconnect after_seq => replay_after sends missed (websocket.py:75-88). Client
  dedup by seq (multiAgentStore:127). disconnect->emit->reconnect(last seq)->receive
  missed->no dup: holds by code. Confidence 0.85.

## SCENARIO 7 — Restart recovery: PARTIAL
- Persist real: runs/instances/tasks/events in SQLite.
- recover() rebuilds ONLY agent_runs (running->interrupted if Hermes dead) +
  task->retryable (recovery_service.py:78-110). NOT: DAG scheduler, route locks,
  worktrees, pending approvals.
- No false-completed: correct, conservative (only interrupted/retryable). Conf 0.80.

## SCENARIO 8 — Worktree isolation: IMPLEMENTED (service), unwired
- 2 coding agents = 2 worktrees (path uses agent_instance_id, worktree_service.py:
  60-64,91; distinct branch 66-70; idempotent reuse). No main-workspace write (cwd=
  worktree path, coding-only). integrate runs on repo_root separately. Per-agent cwd
  set via supervisor.spawn_subagent:114-121 (unwired => live UNVERIFIED). test_phase6
  pass. Confidence 0.80.

## SCENARIO 9 — UI context switch: PARTIAL
- select(id) sets selectedAgentId (multiAgentStore:78-85). Terminal switches
  (termLines by selected.id, :280). Inspector switches (selected:276).
- Browser does NOT switch per agent: hardcoded mock "Awesome App", browserUrl own
  state not bound to agent (MultiAgentWorkspace:899-1003). VIOLATION.
- Orchestrator chat NOT replaced by sub-agent chat: chat=useOrchestratorChat(
  conversationId) independent of selectedAgentId (106). Correct. Confidence 0.85.

## PHASE 6 — UI vs Backend delta table
(UI element | frontend state | API call | backend endpoint | service | DB | event | test | status)

- Orchestrator chat | useOrchestratorChat | sendMessage | POST sessions/{id}/messages
  | session_bridge.submit_message | messages | message_received/assistant_delta |
  test_websocket | REAL (single-agent only)
- Sub-agent board | store.agents | fetchConversationAgents | GET conversations/{id}/
  agents | direct ORM | agent_instances/runs | poll 3s | test_phase8 | REAL but empty
  (nothing spawns instances live)
- Task Graph | taskNodes/edges | fetchConversationTasks | GET conversations/{id}/tasks
  | direct ORM | task_nodes/edges | replan_notification | test_phase8/9 | REAL DAG
- Task edit | version+forms | createTaskNode/Edge | POST/PATCH/DELETE .../tasks |
  conversations.py | task_nodes/edges | replan_notification | test_phase9 | REAL
- Terminal | events[agentId].lines | fetchAgentEvents+WS | GET agents/{id}/events +
  /ws | replay_after | execution_events | terminal_output | — | REAL stream
- Browser preview | browserUrl/browserTab (local) | none | none | none | none | none
  | none | MOCK hardcoded (Awesome App)
- Inspector | selected | (board data) | — | — | — | — | — | PARTIAL (status+run only;
  no model/provider/task/permission)
- Permission popup | permissionQueue | decidePermission + WS | approval via WS |
  resolve_approval | permission_requests | permission_request | — | REAL

Special findings:
- "Live"/"Active" badge (chat header:342) is STATIC, not tied to real stream state.
- Current Task = REAL DAG (not tool-call list). OK.
- Terminal = real terminal_output events, NOT built from chat messages. OK.
- Browser = shared/global mock state, not per-agent session. VIOLATES req 18 + 20.
- App.tsx metrics fallback = random mock when non-Tauri (135-157). Cosmetic.
