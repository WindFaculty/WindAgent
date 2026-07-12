# API + Event Traceability

## REST endpoints (real, file:line)
- POST /api/v1/sessions (sessions.py:39) -> create_session + AgentSessionORM map
- POST /api/v1/sessions/{id}/messages (sessions.py:112) -> submit_message -> start_run
- GET /api/v1/conversations/{id}/agents (conversations.py:33) -> AgentBoardRow
- GET /api/v1/conversations/{id}/tasks (conversations.py:62) -> TaskGraph nodes/edges
- GET /api/v1/agents/{id}/events (conversations.py:112) -> execution_events replay
- PATCH /api/v1/conversations/{id}/tasks/nodes/{id} (conversations.py:232)
- POST /api/v1/conversations/{id}/tasks/nodes (conversations.py:277)
- DELETE .../nodes/{id} (conversations.py:311)
- POST .../tasks/edges (conversations.py:355)
- DELETE .../tasks/edges (conversations.py:411)
- POST /api/v1/tasks/{node_id}/pause (conversations.py:447)
- POST /api/v1/tasks/{node_id}/resume (conversations.py:469)
- POST /api/v1/tasks/{node_id}/cancel (conversations.py:491) -> supervisor.stop_subagent
- POST /api/v1/tasks/{node_id}/retry (conversations.py:535)
- GET/POST /api/v1/worktrees (worktrees.py) -> worktree_service
- WS /ws/{session_id} (websocket.py:55) -> event_bus subscribe + replay
- PATCH /api/v1/providers/{id} (models.py:255) -> api_key plaintext store [S1]

## WebSocket events -> reducers
- message_received / assistant_message_delta -> useOrchestratorChat append (MultiAgentWorkspace:50-74)
- terminal_output -> multiAgentStore.appendEvents (202-205) -> termLines
- permission_request -> enqueuePermission (207)
- permission_granted/denied -> removePermission (209-213)
- replan_notification -> refresh (MultiAgentWorkspace:75-77)
- user_stopped/paused/resumed -> echoed on bus
- error -> generic (session_bridge.py:434)

## Normalized per-agent state
multiAgentStore: state.agents[id], taskNodes[id], taskEdges[], events[agentId]
{seq,lines}. select(id) sets selectedAgentId. Per-agent WS keyed by session_id.
Correct normalized structure. Only violation: WS per-session not per-conversation.

## Event persistence
event_bus publish: seq stamp -> hook persist (execution_events) BEFORE fan-out
(event_bus.py:58-95). Drop on full queue recoverable via replay_after.

## Traceability gaps
- router for spawn_subagent/run_plan/acquire_lock: ABSENT. No API exposes orchestrator
  DAG creation. Frontend cannot trigger live (only manual node add).
- pause/resume/retry/cancel mutate TaskNode.status but no live scheduler consumes them
  (scheduler unwired) => no-op against execution.
- Models/provider PATCH exposes api_key write [S1].
