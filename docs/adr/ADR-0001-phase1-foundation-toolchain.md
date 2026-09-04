# ADR-0001: Phase 1 foundation toolchain

- Status: Accepted
- Date: 2026-09-01
- Phase: 1 (repository foundation)

## Context

`Wind_agent_v2` is a clean-room reimplementation of WindAgent. The old
repository (frozen at `01695ca48dddb7220efd60c212e52dac1d6a5f2d`) is a
behavioural oracle only. Phase 1 must establish engineering infrastructure
before any capability is migrated (plan sections 4 and 37).

## Decision

Backend:

- Python >= 3.12 (uv-managed; old repo pins `>=3.10`, but all of its runtime
  dependencies have 3.12 Windows wheels, so nothing blocks the bump).
- `uv` workspace rooted at `pyproject.toml` with members `backend` and
  `apps/{api,worker,scheduler,cli}`.  `apps/desktop` is reserved for
  Milestone 4.
- One installable foundation distribution: `windagent`
  (`backend/src/windagent/`) containing `kernel/`, `platform/` and
  `modules/` — Phase 2+ fills them; Phase 1 only creates package boundaries
  so the architecture scanner has a stable layout.
- App distributions use `windagent_api`, `windagent_worker`,
  `windagent_scheduler`, `windagent_cli` (src layout).  This avoids
  cross-distribution namespace-package fragility between V2 apps and the
  frozen old repo's identically-named packages.
- Ruff (`E4/E7/E9/F/I/UP`, line-length 100, `py312`), mypy `strict`,
  pytest + pytest-asyncio (`asyncio_mode=auto`), markers copied from the old
  repo (`postgres`, `slow`, `regression`, `multiprocess`, `windows_only`,
  `network`) so parity tests keep speaking one language.
- SQLAlchemy 2 async + Alembic with an async `migrations/env.py`; the URL is
  resolved through `windagent.platform.configuration.Settings`, and any
  `sqlite://` URL outside `WINDAGENT_ENVIRONMENT=test` raises a startup error
  (plan section 8).
- FastAPI exists as a dependency and health-only app factory; routes stay
  empty until Phase 8.
- Alembic starts at zero revisions; `0001_v2_foundation` will be created
  clean in Phase 5 (plan section 9 — no legacy migration history).

Frontend:

- npm workspace rooted at `frontend/package.json` with `app` +
  `packages/{ui,api-sdk,realtime,platform}`.
- React 19, Vite 8, TypeScript ~5.9 `strict` (+`noUncheckedIndexedAccess`,
  `noUnusedLocals/Parameters`, `verbatimModuleSyntax`), TanStack Query v5 as
  the only server-state layer, Zustand v5 for UI state, Vitest 4 (jsdom +
  Testing Library) — the old custom QueryClient and hand-written
  api-contracts are not carried over (plan sections 25 and 27).
- `@windagent/api-sdk` is a small typed fetch boundary today and will be
  replaced by OpenAPI codegen in Phase 8+.

CI (`.github/workflows/ci.yml`) runs from day one: ruff, mypy, unit,
architecture, contract, pip-audit, frontend typecheck, frontend tests,
build, npm audit.

## Consequences

- Every later phase inherits one lockfile (`uv.lock`,
  `frontend/package-lock.json`) and one gate script
  (`scripts/run_gates.ps1`).
- `kernel/`, `platform/` and module directories are intentionally near-empty;
  they are boundary declarations, not implementations.
- The architecture tests encode plan section 35 rules now, so regressions
  against the "V2 became the old repo again" failure mode are caught from
  Phase 2 onward.
