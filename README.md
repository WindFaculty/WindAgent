# WindAgent

WindAgent is a local-first desktop agent built as an Architecture V2 modular
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
               Canonical Architecture V2 packages
```

The former monolithic backend runtime has been retired. Production code,
launchers, CI, and package installation use only the canonical packages above.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+ and npm
- Optional: Rust and Tauri CLI for the desktop bundle
- Optional: PostgreSQL for the authoritative multi-replica profile

## Start the API

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev_api.ps1
```

The API starts at `http://127.0.0.1:8765`. Useful endpoints:

- Liveness: `GET /health/live`
- Readiness: `GET /health/ready`
- OpenAPI: `GET /docs`
- Canonical API: `/api/v2/*`
- Retired API tombstone: `/api/v1/*` returns `410 Gone`

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
- [API V2 contract](docs/api_contract.md)
- [Event protocol](docs/event_protocol.md)
- [Model provider registry](docs/model_provider_registry.md)
- [API V2 package](apps/api/README.md)
- [Worker package](apps/worker/README.md)
- [CLI package](apps/cli/README.md)
- [Desktop client](apps/desktop/README.md)

## License

Internal.
