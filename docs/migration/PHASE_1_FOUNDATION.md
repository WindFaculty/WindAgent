# Phase 1 — repository foundation

Date: 2026-09-01

## Scope delivered

- Repository skeleton exactly per plan section 2: `apps/`,
  `backend/src/windagent/{kernel,platform,modules}`, `frontend/`,
  `migrations/`, `tests/` (9 suites), `migration/`, `deploy/`, `configs/`,
  `scripts/`, `docs/`, root `pyproject.toml`, `compose.yaml`, `README.md`.
- Backend toolchain: uv workspace (Python 3.12.13), Ruff, mypy strict,
  pytest + pytest-asyncio, SQLAlchemy 2 async, Alembic (async env, zero
  revisions — `0001_v2_foundation` is created clean in Phase 5), Pydantic
  v2 settings with the SQLite-rejection startup rule, FastAPI health/readiness
  factory.
- Frontend npm workspace: Vite 8 + React 19 app, TS 5.9 strict, TanStack
  Query v5, Zustand v5, Vitest 4 (jsdom + Testing Library), packages
  `ui` / `api-sdk` / `realtime` / `platform`.
- CI (`.github/workflows/ci.yml`) from day one: lint, typecheck, unit,
  architecture, contract, security audits, build.
- Architecture gate tests encode plan section 35 (see
  `docs/architecture/FOUNDATION.md`); ADR-0001 records toolchain decisions.
- Local one-command gate: `scripts/run_gates.ps1`.

## Gate results (plan section 4)

```text
uv sync             PASS   (47 packages, Python 3.12.13)
ruff check          PASS   (All checks passed)
mypy typecheck      PASS   (45 files, 0 issues)
pytest              PASS   (20 tests: unit + contract + architecture)
frontend typecheck  PASS   (tsc strict, 5 workspaces)
frontend test       PASS   (9 tests: platform, api-sdk, realtime, ui, app)
frontend build      PASS   (vite build)
npm audit           PASS   (0 vulnerabilities)
phase0 manifests    PASS   (56 capabilities still FROZEN)
```

## Explicitly NOT done in Phase 1

No business capability, no ORM models, no routes beyond health/readiness, no
job runtime, no WebSocket transport, no copy of any old source file. Kernel
and platform packages are boundary placeholders until Phases 2–3.

## Next

Phase 2 — Kernel: `EntityId`, `CorrelationId`, `DomainError`, `Result[T]`,
`DomainEvent`, `EventEnvelope`, `Clock`, `Money`, `Version` — written from
scratch with the kernel import-free gate already green.
