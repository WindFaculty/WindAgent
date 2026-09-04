# WindAgent V2

Clean-room reimplementation of WindAgent.  The old repository
(`../WindAgent`, frozen at `01695ca4`) is a behavioural specification and
parity oracle — **never** an import target.

Phases 0–10 establish the frozen baseline and the engineering, kernel,
platform-contract, module-runtime, persistence, event, durable-job, worker,
API, security, and observability foundations. The clean migration chain is
now `0001 → 0002 → 0003 → 0004`; no business capability has been migrated.

Phase 7 supplies priority/FIFO submission, idempotency, PostgreSQL
`SKIP LOCKED` claims plus guarded CAS, renewable leases, fencing tokens,
retry, timeout, cancellation, crash recovery, atomic result/outbox
finalization, module-driven handler registration, and the opt-in
`/debug/jobs` + websocket vertical slice.

Phase 10 completes Milestone 1 with W3C trace propagation, task-local causal
context, JSON logs with secret redaction, bounded metrics exposed at
`/metrics`, HTTP/command/query/worker spans, contextual security audit, and
durable job trace/actor propagation. Phase 11 (Model Gateway) is the next
business-module migration.

## Layout

```text
apps/       api | worker | scheduler | cli | desktop (reserved)
backend/    src/windagent/{kernel,platform,modules}
frontend/   app (Vite+React) + packages/{ui,api-sdk,realtime,platform}
migrations/ Alembic (async, PostgreSQL-only)
tests/      architecture | unit | contract | integration | parity |
            e2e | reliability | security | performance
migration/  manifests (Phase 0 baseline) | importers | parity
docs/       architecture | adr | migration
configs/    non-secret defaults
deploy/     release manifests (later milestones)
```

## Getting started

```powershell
uv sync                     # installs all workspace members editable
docker compose up -d postgres   # optional: local PostgreSQL 16 on :55433
uv run pytest               # unit + architecture + contract gates
uv run uvicorn windagent_api.app:app --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run typecheck
npm test
npm run build
```

## Gates (Phase 1)

| Gate                | Command                     |
| ------------------- | --------------------------- |
| dependency install  | `uv sync`                   |
| python lint         | `uv run ruff check .`       |
| python typecheck    | `uv run mypy`               |
| python tests        | `uv run pytest`             |
| manifest baseline   | `uv run python scripts/validate_phase0_manifests.py` |
| frontend typecheck  | `cd frontend && npm run typecheck` |
| frontend tests      | `cd frontend && npm test`   |
| frontend build      | `cd frontend && npm run build` |

`scripts/run_gates.ps1` runs the whole table in order.

## Hard rules (enforced by `tests/architecture/` and CI)

1. Nothing in V2 imports the old WindAgent packages.
2. `kernel` stays pure: no FastAPI/SQLAlchemy/httpx/pydantic, no platform or
   module imports.
3. `platform` is domain-agnostic: no feature vocabulary, no module imports.
4. Feature modules never import each other; they communicate through platform
   contracts only.
5. PostgreSQL is canonical everywhere; SQLite is rejected at startup outside
   isolated tests (`WINDAGENT_ENVIRONMENT=test`).

## Migration status

See `docs/migration/MIGRATION_STATUS.md`. Phase records live under
`docs/migration/PHASE_*.md`; the phase 0–6 reassessment is recorded in
`docs/migration/PHASE_0_6_AUDIT.md`.
