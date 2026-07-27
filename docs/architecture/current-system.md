# WindAgent — Current System Baseline

> Historical Phase 0 snapshot only. It describes the pre-cutover monolith and
> is not an authoritative runtime or launch guide. The Architecture V2 package
> map and commands in the repository root README are current.

Phase 0 snapshot of the legacy monolith before Architecture V2 restructuring.
No behavior changes; this is inventory and contract capture.

## Repository

- Path: `D:\code_ca_nhan\WindAgent`
- Branch: `refactor/architecture-v2-phase-00-baseline`
- Starting SHA: `7e1cd9fa1ed38f33edc68f323df45c3b9d1fc28e`
- Remote SHA: no upstream configured
- Python: 3.11.15
- Node: v22.23.1, npm 10.9.8
- Rust/cargo: 1.97.1
- Tauri: `@tauri-apps/cli` ^2.0.0, `@tauri-apps/api` ^2.11.1

## Layout

```text
WindAgent/
├── apps/
│   ├── backend/          # FastAPI sidecar (current monolith)
│   └── desktop/          # Tauri + React + Vite frontend
├── artifacts/            # Runtime artifacts, reports, audit logs
├── docs/                 # Existing docs
├── ban_ke_hoach.md       # Master plan
└── README.md
```

## Backend (`apps/backend`)

- Version: 0.8.0 in `main.py`, project version 0.3.0 in `pyproject.toml`
- Framework: FastAPI + Pydantic v2 + SQLAlchemy 2.0 + aiosqlite
- Migration tool: Alembic, head `2222ab020b94`
- Database: SQLite (`windagent.db`)
- Tables: 31 (including `alembic_version`)
- Python files: 1700, lines ~749k (includes artifacts/logs/txt counted as `.py` due to mixed files; real source smaller)
- Test command: `cd apps/backend && WINDAGENT_MODEL_BACKEND=mock uv run pytest tests -q`

### Routers mounted in `main.py`

- `/health` (root + `/api/v1`)
- `/ws/{session_id}` WebSocket (root)
- `/v1/chat/completions` (root, compatibility)
- `/models/health` compatibility alias
- `/api/v1` prefix: health, sessions, permissions, workflow, tools, agents, hermes, agent-s3, models, worktrees, events (+ recover router), browser
- `/api/v1/conversations` (mounted without additional prefix)
- Self-prefixed: model_routing (`/models/routing`, `/v1`, `/router/runtime`), openai_compatible (`/v1`), router_observability (`/router/runtime`)

### Services (high-level)

- `db/database.py`, `db/models.py` — persistence and ORM
- `services/event_bus.py` + `event_hooks.py` — in-memory pub/sub, DB + JSONL persistence
- `services/model_client.py`, `model_service.py` — model provider client + catalog/quota
- `services/planner_service.py` — planner wrapper
- `services/route_lock_service.py` — canonical model pinning
- `services/router_policy.py`, `router_execution_service.py`, `provider_gateway.py` — model routing runtime
- `services/tool_executor.py`, `tool_registry.py` — tool execution
- `services/permission_service.py` — permission requests
- `services/workflow_runner.py`, `workflow_service.py` — workflow engine
- `services/dag_scheduler.py` — DAG orchestration
- `services/session_service.py` — chat session management
- `services/hermes/` — Hermes runtime bridge (runtime_manager, api_client, session_bridge, supervisor)
- `services/worktree_service.py` — git worktree isolation
- `services/browser_service.py` — browser automation bridge
- `services/recovery_service.py` — durable event replay / recovery
- `services/agent_*` — Agent-S3 integration adapters and executor

## Frontend (`apps/desktop`)

- Framework: Tauri 2.x + React 18 + TypeScript + Vite + Vitest
- State: Redux Toolkit + Zustand
- Version: 0.6.0
- Scripts: `dev`, `build`, `preview`, `type-check`, `tauri`, `test`
- Build: `npm run build` passes
- Type-check: passes
- Test command: `npm run test`

## Database migration status

Alembic head: `2222ab020b94` (add session recovery columns).
No unapplied migrations.

## Known issues at baseline

- Backend tests: 11 failures in session recovery / G25 area.
- Frontend tests: 4 failures in agent session store/socket/recovery.
- These are pre-existing; Phase 0 does not fix them.

## Artifacts produced in Phase 0

- `artifacts/architecture_v2/baseline/api_inventory.json`
- `artifacts/architecture_v2/baseline/event_inventory.json`
- `artifacts/architecture_v2/baseline/database_inventory.json`
- `artifacts/architecture_v2/baseline/dependency_graph.json`
- `artifacts/architecture_v2/baseline/baseline_receipt.json`
- `docs/architecture/current-system.md`
- `docs/architecture/legacy-dependency-map.md`
