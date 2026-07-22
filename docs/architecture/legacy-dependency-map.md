# Legacy Dependency Map

High-level construction order in `apps/backend/main.py`.
Edges show runtime assembly, not import graph.

```text
main.py lifespan
├── Database (SQLite + aiosqlite)
│   └── init_models() creates tables from db.models
├── EventBus
│   ├── add_publisher_hook(make_execution_event_hook(db))
│   └── add_publisher_hook(make_jsonl_event_hook(artifacts_root))
├── GuiAdapter (Mock or PyAutoGUI)
├── GuiGroundingService (mock default)
├── ToolExecutor(event_bus, db, gui, grounding_service)
├── ModelClient (mock or Ollama)
├── PlannerService(model_client)
├── SessionService(event_bus, db)
├── WorkflowService(event_bus, db, planner)
├── PermissionService(event_bus)
├── WorkflowRunner(event_bus, executor, session_service, workflow_service, permission_service)
├── ModelService(db, model_client)
│   └── init_database_seeds()
├── RouteLockService(db)
├── AgentRegistryService(db)
│   └── init_database_seeds()
├── BrowserService(event_bus, artifacts_root)
├── HermesRuntimeManager(hermes_config, event_bus)
├── HermesApiClient(hermes_config)
├── HermesSessionBridge(db, hermes_api_client, event_bus, browser_service)
├── DAGScheduler(db, event_bus)
├── HermesSupervisor(db, bridge, event_bus, worktree_service)
├── RecoveryManager(db, hermes_api_client)
│   └── seed_seq -> EventBus
├── RouterPolicy / RouterExecutionService / ProviderGateway
│   └── wired into ModelService + PlannerService
└── AgentS3Adapter (conditional, env opt-in)
    └── AgentS3StepExecutor wired into ToolExecutor
```

## Dependency direction

- `apps/backend/routers` depend on services via `request.app.state`.
- `services` depend on each other by constructor injection inside `lifespan`.
- `db.models` is leaf; no business logic.
- `schemas` are leaf.
- `utils.encryption` is used by `db.models` and services.

## Event flow

```text
Producer (router/service)
  ↓ EventBus.publish(session_id, envelope)
  ├── hook 1 → insert execution_events (DB)
  ├── hook 2 → append artifacts/runs/{id}/events.jsonl
  └── fan-out → WebSocket subscribers / internal consumers
```

## Storage flow

```text
App state services
  ↓ SQLAlchemy async session
  └── SQLite windagent.db (31 tables)
```

## Known coupling

- `main.py` constructs every service; moving service wiring requires extracting composition root.
- Several service modules import sibling services directly rather than via injected abstractions.
- Model / routing / provider logic mixes provider Gateway and execution service.
- Frontend `App.tsx` carries many route-managed states; session recovery store is partly implemented.

## API/WS surface summary

- REST routes: ~119 entries including path aliases and prefixes.
- WebSocket: `/ws/{session_id}` via `routers/websocket.py`.
- Event protocol: 44 event types defined in `schemas/event.py`.
