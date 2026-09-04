# Phase 12 — Automation / Tool Runtime (Milestone 2: Agent Platform)

**Date:** 2026-09-02  
**Status:** Cut over  
**Scope:** Consolidate the scattered tool + execution implementation into a single bounded context under `modules/automation/` per plan section 18.

## Source → Target

Old locations (frozen reference, not imported):

```
tools/*                    → modules/automation/domain/*  (ToolDefinition, ToolRiskLevel, ToolInvocation, ToolResult)
tools/windagent_tools/*    → modules/automation/infrastructure/adapters/in_process  (read_file/write_file + registry)
tools/windagent_tools/shell        → modules/automation/infrastructure/adapters/subprocess (SafeShellRunner parity)
tools/windagent_tools/browser      → modules/automation/infrastructure/adapters/browser (Playwright stub, consent-gated)
tools/windagent_tools/mcp           → modules/automation/infrastructure/adapters/mcp (stdio/SSE stub)
execution/*                → modules/automation/application/executor + registry + policy
execution/adapters/*       → modules/automation/infrastructure/adapters/*  (7 runtimes)
windagent_core/contracts/tools/*  → modules/automation/domain/*  (frozen metadata contracts, no legacy import)
storage/tool_runs (implicit)     → modules/automation/infrastructure/* (durable runs)
apps/api tool routes               → modules/automation/api/routes.py  (thin FastAPI router under /api/v4/automation)
```

Target layout (plan section 18 exact):

```
modules/automation/
├── public/                 # public re-exports for composition roots & tests
├── domain/
│   ├── definition.py       # ToolRiskLevel (7 levels), RuntimeType (7 runtimes), ToolDefinition (frozen)
│   ├── invocation.py       # ToolInvocation + ToolExecutionContext (immutable, validated)
│   ├── result.py           # ToolResult (canonical success/failure + timing)
│   ├── sandbox.py          # PathSandbox parity (resolve + relative_to, symlink-aware)
│   ├── policy_mapping.py   # HIGH_RISK_LEVELS, HARD_DENY, POLICY_GATED_* + is_policy_gated
│   └── errors.py           # AutomationError hierarchy (forbidden/conflict/validation/not_found)
├── application/
│   ├── commands.py         # 5 commands: RegisterTool/UpdateTool/DeregisterTool/ExecuteTool/RegisterBuiltinTools
│   ├── queries.py          # 8 queries: GetTool/GetToolByName/ListTools/GetToolRun/.../ListRuntimeTypes/GetCapabilities
│   ├── ports.py            # AutomationStore + TransactionScope (UoW + outbox)
│   ├── models.py           # durable rows (ToolRow/ToolRunRow) + view DTOs (ToolView/ToolRunView)
│   ├── services.py         # orchestrator (one TransactionScope per command, atomic outbox, CAS)
│   ├── handlers.py         # Command/Query handlers (ambient AutomationServices)
│   ├── runtime.py          # AutomationServices + ContextVar binding (mirrors model_gateway/studio)
│   ├── registry.py         # ToolRegistry (collision-safe, capability index) + RuntimeRegistry (7 adapters)
│   ├── executor.py         # ToolExecutor (registry → policy → runtime dispatch)
│   ├── policy.py           # Policy helper (hard-deny + path-scope + destructive-guard + engine delegate)
│   └── events.py           # 7 automation.* envelopes (tool.registered/updated/deregistered/invoked/succeeded/failed/denied)
├── infrastructure/
│   ├── tables.py           # 2 automation_* tables registered into shared metadata (0008)
│   ├── repository.py       # SqlAutomationStore + SqlTransactionScope (CAS optimistic_version)
│   ├── memory.py           # InMemoryAutomationStore + InMemoryTransactionScope (offline tests)
│   └── adapters/
│       ├── base.py         # ToolRuntimeAdapter protocol
│       ├── in_process.py   # InProcessAdapter (read_file/write_file/echo + registered callables)
│       ├── subprocess.py   # SubprocessAdapter (asyncio subprocess, timeout, cwd sandbox, stdout/stderr)
│       ├── browser.py      # BrowserAdapter (Playwright stub, consent-gated)
│       ├── mcp.py          # McpAdapter (stdio/SSE stub, server/tool validation)
│       ├── desktop.py      # DesktopAdapter (Tauri IPC stub)
│       ├── container.py    # ContainerAdapter (Docker stub)
│       └── remote.py       # RemoteAdapter (HTTP remote stub, endpoint validation)
├── api/
│   └── routes.py           # /api/v4/automation/* — 13 endpoints, policy-gated, bus-dispatched
├── jobs/
│   └── handlers.py         # automation.tool.execute (durable, fencing-protected, policy-aware)
├── manifest.py             # ModuleManifest (5 commands, 8 queries, 1 job, 1 router, 10 capabilities)
└── __init__.py
```

## Invariants preserved (EXTRACT_LOGIC)

- **ToolDefinition:** frozen from `windagent_core.contracts.tools.metadata.ToolDefinition` + `windagent_tools.base.ToolDefinition` (name non-blank, version, 7 `ToolRiskLevel` values, `capability`, `runtime_type`, `side_effect_class`, `sandbox_requirement`, `required_permissions`, schemas). Every field validated in `__post_init__`; `to_dict`/`from_dict` round-trip is deterministic. No implementation leaks into the domain type.
- **Invocation/Result:** `ToolInvocation` requires non-blank `tool_name`, validates `timeout_seconds > 0`, freezes `params` shallow copy; alias `arguments` kept for parity. `ToolResult` carries `execution_time_ms` and `completed_at` with non-negative timing.
- **Registry:** `register_tool` rejects namespace collision unless `override_collision=True` (old `DomainError` WINDAGENT_ERR_TOOL_NAMESPACE_COLLISION preserved as `AutomationConflictError` with `conflict` code). Capability index is maintained on register/remove; `list_by_capability` and audit log are deterministic.
- **Risk → Policy mapping:** `HIGH_RISK_LEVELS` = `{external_network, secret_access, process_execution, destructive, privileged}` (identical to old `HIGH_RISK_LEVELS`). `HARD_DENY_ACTIONS` = `{format_c, drop_production_db, exfiltrate_keys, bypass_auth}` always deny. Path-scope via `is_within_workspace` (resolve + `relative_to`, symlink-aware) denies when `target` escapes `workspace_root`. Destructive without `user_approved` yields `REQUIRE_APPROVAL` before engine (old `DESTRUCTIVE_GUARD_POLICY`). `is_policy_gated` returns true for `shell|filesystem|browser` capabilities and `process|filesystem` side effects — **shell, filesystem write, browser side effect bắt buộc đi qua Policy Engine** (plan section 18).
- **Sandbox:** `resolve_safe_path` joins relative paths onto `workspace_root` before `resolve()` (avoids cwd leakage), enforces `relative_to` containment, rejects empty paths — parity with `windagent_tools.filesystem.sandbox.PathSandbox` + `normalize_and_validate_path`.
- **ExecutionRuntime routing:** `RuntimeRegistry` maps 7 `RuntimeType` values to adapters (old `ExecutionRuntimeRegistry.resolve_adapter` prefix rules preserved as explicit `runtime_type` on the definition — no prefix heuristic needed; fallback to `in_process` when a specific runtime missing). Each adapter implements `ToolRuntimeAdapter.execute` and never raises (returns `ToolResult` with `success=False` on failure).
- **Fencing/Outbox:** Every mutating command runs in `TransactionScope` (platform UoW + `TransactionalOutbox`) so the domain write and the `automation.*` event commit atomically. `optimistic_version` CAS via `expected_version` is enforced in SQL (`WHERE optimistic_version = :expected_version`) and mirrored in memory.

## Architecture gates

- `test_kernel_does_not_import_infrastructure` — PASS (kernel pure)
- `test_platform_*` — PASS (platform still domain-agnostic)
- `test_modules_do_not_import_each_other` — PASS (automation only imports `windagent.kernel` + `windagent.platform` + own package)
- `test_no_v2_file_imports_legacy` — PASS (no `windagent_core` / `windagent_tools` / `windagent_execution` imports)
- `test_platform_contracts_only_depend_on_kernel_and_stdlib` — PASS
- `test_sqlite_is_not_a_default` — PASS (automation adds no `sqlite` string; only `platform/configuration/settings.py` may mention it)

`ruff check backend/src/windagent/modules/automation` — **All checks passed**  
`mypy --config-file pyproject.toml` — **0 errors in automation** (full repo 1 pre-existing error in `live_record` adapter unrelated)

## Persistence

- **Migration `0008_automation`** creates 2 tables with FK-free, prefix-namespaced design (single Alembic chain, no legacy 31 revisions copied):
  `automation_tools` (PK `tool_id`, unique `name`, `risk_level`, `capability`, `runtime_type`, `side_effect_class`, `sandbox_requirement`, `required_permissions_json`, `artifact_outputs_json`, `parameters_schema_json`, `output_schema_json`, `enabled`, `optimistic_version` + timestamps), `automation_tool_runs` (PK `run_id`, `tool_name`, `invocation_id` indexed, `workspace_root`, `actor_id`, `correlation_id`, `causation_id`, `trace_id`, `runtime_type`, `status`, `result_json`, `error`, `execution_time_ms`, `policy_decision_json`, `created_at`, `completed_at`).
- `SqlAutomationStore` implements `AutomationStore` with `INSERT` uniqueness checks and `UPDATE … WHERE optimistic_version = :expected_version` CAS; `SqlTransactionScope` joins the caller's `SqlUnitOfWork` and records exactly one `automation.*` event via `TransactionalOutbox`.
- `InMemoryAutomationStore` mirrors the same CAS semantics for offline unit tests (`memory_scope_factory`).

## Application layer

- **Commands** are frozen dataclasses extending `Command[View]`; **Queries** extend `Query[View]`. No command builds provider or infra concerns.
- **AutomationService** is the only place that knows the definition → row and run → row mapping; handlers are thin (`container_for(services).automation.*`). `execute_tool` hydrates the registry from the store when needed, creates a `pending` run, dispatches via `ToolExecutor`, then atomically updates the run with `result`/`error`/`policy_decision` and records `succeeded/failed/denied`.
- **ToolRegistry + RuntimeRegistry:** `ToolRegistry` holds `ToolDefinition` by `name` with capability index and audit log; `RuntimeRegistry` holds the 7 adapters (`in_process`, `subprocess`, `browser`, `mcp`, `desktop`, `container`, `remote`). Both are injectable for tests.
- **ToolExecutor:** `registry.require(name)` → `evaluate_policy(engine, definition, invocation, ctx)` (hard-deny, path-scope, destructive-guard, then platform engine delegate) → `runtime_registry.get(runtime_type)` (fallback `in_process`) → `adapter.execute`. Policy denial raises `AutomationPolicyDeniedError` (`forbidden` → 403) or `AutomationPolicyApprovalRequiredError` (`conflict` → 409) so the API maps correctly via `DEFAULT_CODE_STATUS`.
- **Outbox:** Every mutating command records one envelope (`automation.tool.registered/updated/deregistered/invoked/succeeded/failed/denied`) before `commit()`.

## API

- Prefix `/api/v4/automation` (canonical `/api/v4`, not `Wind_agent_v2` folder name).
- 13 endpoints across 4 sub-resources:
  - tools `POST /tools`, `GET /tools` (capability/runtime_type/enabled_only filters), `GET /tools/{tool_id}`, `GET /tools/by-name/{name}`, `PATCH /tools/{tool_id}`, `DELETE /tools/{tool_id}`, `POST /tools/builtins/register` (idempotent 16-tool catalog)
  - execution `POST /tools/{tool_name}/execute` (params + workspace_root + actor/correlation + user_approved → ToolRunView)
  - runs `GET /runs` (tool_name/status/limit), `GET /runs/{run_id}`, `GET /runs/by-invocation/{invocation_id}`
  - meta `GET /runtimes` (7 types), `GET /capabilities` (bucket by capability)
- Each route validates via Pydantic DTO, dispatches via `command_bus`/`query_bus`, and maps via `View.to_payload()`. Mutating routes require `automation.write`, reads require `automation.read`, execution requires `automation.execute` (policy engine, audited; unconfigured engine allows in dev — `POLICY_UNCONFIGURED_POLICY_ID`).
- Domain policy (shell/filesystem/browser) is enforced **inside** `ToolExecutor` even when HTTP auth already passed — defense in depth per plan 18.

## Jobs

- `automation.tool.execute` — durable, fencing-protected job that calls `AutomationService.execute_tool` via the same outbox-backed path. Payload: `{tool_name, params, workspace_root, actor_id, correlation_id, causation_id, trace_id, user_approved, invocation_id}`. Policy denials are returned as `{status: "denied", error}` (non-retryable) so the worker does not retry indefinitely. Future wiring: agent_runtime will submit this job type through the platform `DurableJobQueue` seam (no cross-module import).

## Module manifest

- `manifest = build_automation_manifest()` exposes:
  - 5 `CommandRegistration`s
  - 8 `QueryRegistration`s
  - 1 `JobRegistration` (`automation.tool.execute`)
  - 1 router (`create_automation_router()`)
  - capabilities `("automation","tools","execution","in_process","subprocess","browser","mcp","desktop","container","remote")`
- Discovered automatically by `PackageModuleDiscovery` (no bootstrap file lists it by name).

## Verification

- **Ruff:** `ruff check backend/src/windagent/modules/automation` — 0 errors, 0 warnings.
- **Mypy strict:** `mypy --config-file pyproject.toml` — 0 errors in automation (full repo 1 pre-existing error in `live_record/infrastructure/repository.py:426` — `type: ignore[index]` unused, not introduced by automation).
- **Architecture:** 8/8 architecture tests pass (including `test_sqlite_is_not_a_default` and `test_modules_do_not_import_each_other`).
- **Unit (offline):** `pytest tests/unit -k "not postgres"` — 277 passed (baseline 266 + 11 new isolation via InMemoryAutomationStore + registry/executor/policy unit checks). Full offline `pytest tests/unit` — 277 passed, `pytest tests/architecture` — 8 passed.
- **SQLite (file):** `sqlite+aiosqlite:////tmp/automation_test.db` via `SqlAutomationStore` + `metadata.create_all` — register → duplicate reject → list → execute read_file → write_file inside workspace → path traversal deny (outside workspace → `AutomationPolicyDeniedError` / 403) → exec_shell without approval → 409 `destructive-guard` → exec_shell with approval → 200 `subprocess` → browser/mcp/container/remote stubs verified.
- **API (file DB):** `/api/v4/automation` E2E via `httpx.ASGITransport` + `create_app(Settings(environment="test", database_url="sqlite+..."))` — `GET /tools` (0) → `POST /tools/builtins/register` (16) → `GET /tools` (16) → `POST /tools/read_file/execute` (200, policy allow-no-engine) → `POST /tools/exec_shell/execute` without approval (409) → with approval (200, subprocess) → `GET /runs` (3) → `GET /runtimes` (7) → `GET /capabilities` (12). `PlatformModuleDiscovery` also finds `automation 1.0.0` alongside `model_gateway`, `studio`, `production`, `live_record`.
- **Migrations:** `alembic upgrade head` (test SQLite) — 0007 → 0008 → 0009 chain clean, `downgrade` → `upgrade` round-trip preserves `automation_tools`/`automation_tool_runs` and `ix_*` indexes; PostgreSQL 16 integration path unchanged (12 tests, `SKIP LOCKED`/`fencing`/`outbox` still green).

## Cutover notes

- No V2 file imports `../tools`, `../execution`, `../windagent_tools`, or `../windagent_execution`.
- `tools/*` and `execution/*` remain frozen; data migration will flow through importers, not through this schema history.
- Frontend modules will be built in a later phase (Milestone 4) against the generated `@windagent/api-sdk` from this backend.
- The 7 runtime adapters are intentional stubs for `browser`/`mcp`/`desktop`/`container`/`remote`; their contracts are frozen and offline-simulated, but native hardening (Playwright session lifecycle, WGC/NVENC, Docker isolation, MCP stdio/SSE) will be wired through the same `ToolRuntimeAdapter` seam without changing the manifest or the API.

## Definition of Done (plan section 18)

- [x] Single bounded context `modules/automation` owns ToolDefinition/ToolRegistry/ToolPolicy/ToolExecutor/ExecutionRuntime
- [x] Domain is pure (no FastAPI/SQLAlchemy/httpx), `ruff` + `mypy` clean
- [x] Persistence is PostgreSQL-canonical with `0008` migration, plus in-memory adapter for tests
- [x] Events are atomic via outbox, with 7 `automation.*` envelopes
- [x] API is `/api/v4/automation`, thin, bus-dispatched, policy-gated (HTTP) + domain-gated (executor)
- [x] Runtime adapters `in_process|subprocess|browser|mcp|desktop|container|remote` are declared, registered, and discoverable; `shell/filesystem write/browser side effect` are proven to be policy-gated (409 without approval, 403 on hard-deny/path-escape)
- [x] Job seam `automation.tool.execute` is durable and worker-discoverable
- [x] Module is auto-discoverable, no bootstrap edit required

