# Database Schema Audit

Engine: SQLite (sqlite+aiosqlite). Init: db.init_models() => Base.metadata.create_all.
NO Alembic / versioned migrations. seed_canonical_models non-destructive insert, not
migration. create_all NOT production-ready (per audit rules).

## Tables -> requirement
- chat_sessions (35) : conversation
- agent_sessions (642) : session (windagent) -> Hermes bridge map
- agent_instances (464) : agent instance (conversation_id, NO FK)
- messages (53) : message
- workflows (72) / workflow_steps (93) : legacy linear path
- parent_tasks (371) : parent task (conversation_id NO FK, NO unique)
- task_plans (390) : task plan FK parent_task_id
- task_nodes (406) : task node FK plan_id
- task_edges (431) : task edge FK plan_id, from/to FK task_nodes
- task_artifacts (447) : task artifact FK task_nodes
- agent_runs (480) : agent run FK agent_instance_id
- canonical_models (282) : canonical model
- provider_model_bindings (300) : provider binding FK canonical
- route_locks (323) : route lock FK canonical
- route_attempts (345) : route attempt FK route_lock
- execution_events (137) : event seq (event_seq nullable, NO unique(session_id,seq))
- permission_requests (663) : permission
- worktrees (499) : worktree
- tool_calls (128) : idempotency_key column (unused live)

## Dangerous assumptions (confirmed)
1. session_bridge queries AgentSessionORM by windagent_session_id scalar_one_or_none
   (sessions.py:117, websocket.py:206, session_bridge.py:259). NO unique constraint.
   Future N-agent-per-session => MultipleResultsFound. HIGH.
2. parent_tasks.conversation_id / agent_instances.conversation_id: loose string, NO FK,
   NO index. Conversation loose join across tables. MED.
3. conversations.task_graph picks ParentTaskORM by conversation_id .first() (68-72).
   Silently one parent if multiple exist. MED.
4. execution_events.event_seq nullable, no per-session UNIQUE. DB does not enforce
   monotonic/unique; dedup client-side only. MED.
5. task_nodes/edges/artifacts FK to plan/nodes: NO cascade. Plan delete => orphans. MED.
6. SQLite single-writer, no WAL configured. Parallel fan-out write contention. MED,
   unverified runtime.

## Migration mechanism
create_all only. No Alembic. Recommend versioned migrations before prod. HIGH (process).
