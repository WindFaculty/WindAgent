# WindAgent

WindAgent is a local-first desktop agent built as an Architecture V3 modular
monolith. The runtime is split into independently installable API, Worker, and
CLI applications over shared canonical packages and persistent storage.

## Runtime architecture

```text
apps/api       FastAPI REST, SSE, and WebSocket entrypoint
apps/worker    Durable background execution process
apps/cli       Doctor, architecture, and workflow commands
apps/desktop   Tauri + React desktop client
apps/web       React web client

core, orchestration, execution, intelligence, providers, tools, workflows,
verification, context, memory, storage, observability, evals, plugins, skills
               Canonical Architecture V3 packages
```

The former monolithic backend runtime has been retired. Production code,
launchers, CI, and package installation use only the canonical packages above.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+ and npm
- Optional: Rust and Tauri CLI for the desktop bundle
- Optional: Docker Desktop (WSL2 backend) for the local PostgreSQL — see below
- Optional: a machine-installed PostgreSQL for the authoritative multi-replica profile

## PostgreSQL via Docker (local dev/tests)

Production runs on real PostgreSQL 16. Locally, `compose.yaml` provisions the
same thing with the exact credentials CI uses (`test:test`, database
`windagent`), so test semantics match `.github/workflows/ci.yaml`. The host
port defaults to `55432` to coexist with any locally installed PostgreSQL.
Override it via `--port`, the `WINDAGENT_POSTGRES_PORT` shell variable, or a
repo-root `.env` copied from `.env.example` — all three reach both Docker and
the wrapper (the wrapper injects the resolved port into `docker compose`, so
the published mapping can never drift from the URL it dials).

```powershell
# Start + wait until pg_isready reports healthy (no blind sleeps)
.venv\Scripts\python.exe scripts\dev_postgres.py up

# One-shot real-PostgreSQL test run:
#   ephemeral database -> Alembic migrations -> backend identity attestation
#   -> pytest -m postgres -> drop the ephemeral database.
# On ANY failure the database and evidence under artifacts/ci/dev-postgres/
# are kept for inspection.
.venv\Scripts\python.exe scripts\dev_postgres.py test
```

Extra pytest arguments replace the default `-m postgres` selection:

```powershell
.venv\Scripts\python.exe scripts\dev_postgres.py test -- tests/contracts/test_p1_pg_idempotency_atomicity_cas.py -q
```

Other subcommands: `status`, `url [--db NAME]`, `migrate [--db NAME]`,
`psql-drop --db NAME`, and `down [--clean]` (`--clean` also deletes the data
volume). Migrations always run through the canonical programmatic runner
(`windagent_storage.migrations.runner`) — never hand-written DDL.

The desktop recording stack (Tauri/WGC/WASAPI/NVENC) is Windows-native and is
never dockerized; only PostgreSQL runs in Docker here.

## Start the API

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev_api.ps1
```

The API starts at `http://127.0.0.1:8765`. Useful endpoints:

- Liveness: `GET /health/live`
- Readiness: `GET /health/ready`
- OpenAPI: `GET /docs`
- Canonical API: `/api/v3/*`
- Realtime WebSocket: `/ws`
- Retired API tombstones: `/api/v1/*` and `/api/v2/*` return `410 Gone`

API and Worker must use the same `WINDAGENT_DATABASE_URL`.

## Start a client

Desktop/Tauri frontend:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev_desktop.ps1
```

Web frontend:

```powershell
cd apps/web
npm ci
npm run dev
```

## Verify the workspace

```powershell
powershell -ExecutionPolicy Bypass -File scripts\healthcheck.ps1

$env:UV_CACHE_DIR = "$PWD\.tmp-uv-cache"
uv run python scripts/check_architecture_imports.py
uv run pytest

cd apps/desktop
npm ci
npm test -- --run
npx tsc --noEmit
npm run build

cd ..\web
npm ci
npm test -- --run
npm run typecheck
npm run build
```

The architecture checker is fail-closed for the retired runtime path and for
canonical-to-legacy imports.

## Documentation

- [Current roadmap — WindAgent Studio Roadmap 1](road_map.md)
- [3D Animation production plan](docs/video_production/3d_animation_plans/README.md)
- [API V3 contract](docs/api_contract.md)
- [Event protocol](docs/event_protocol.md)
- [Model provider registry](docs/model_provider_registry.md)
- [API package](apps/api/README.md)
- [Worker package](apps/worker/README.md)
- [CLI package](apps/cli/README.md)
- [Desktop client](apps/desktop/README.md)

## License

Internal.
