# WindAgent Architecture V3 API Contract

## Authority and versioning

`windagent_api.main:app` is the only ASGI application authority.

- Canonical resources use `/api/v3/*` (unified business and studio API).
- Realtime WebSocket is served at root `/ws`.
- Legacy `/api/v1/*` and `/api/v2/*` requests return `410 Gone` (permanent tombstones with migration guide pointing to `/api/v3/*`).
- Health endpoints remain unversioned so orchestrators can probe them without binding to a business API version.

Source of truth for this table: router registration in
`apps/api/windagent_api/main.py` + `apps/api/windagent_api/routers/v3/`.

## Health

| Method | Path | Purpose |
|---|---|---|
| GET | `/health/live` | Process liveness |
| GET | `/health/ready` | Dependency-aware readiness |
| GET | `/internal/architecture` | Architecture and version metadata |

## Realtime WebSocket

| Transport | Path | Description |
|---|---|---|
| WS | `/ws` | Canonical WebSocket endpoint for RealtimeProvider events, subscriptions, replay, and live broadcast |

## Projects and Episodes

| Method | Path |
|---|---|
| POST | `/api/v3/projects` |
| GET | `/api/v3/projects` |
| GET | `/api/v3/projects/{project_id}` |
| PUT | `/api/v3/projects/{project_id}` |
| DELETE | `/api/v3/projects/{project_id}` |
| POST | `/api/v3/projects/{project_id}/episodes` |
| GET | `/api/v3/projects/{project_id}/episodes` |
| GET | `/api/v3/projects/{project_id}/episodes/{episode_id}` |
| PUT | `/api/v3/projects/{project_id}/episodes/{episode_id}` |
| DELETE | `/api/v3/projects/{project_id}/episodes/{episode_id}` |

## Tasks and Workflows

| Method | Path |
|---|---|
| POST | `/api/v3/tasks` |
| GET | `/api/v3/tasks` |
| GET | `/api/v3/tasks/{task_id}` |
| POST | `/api/v3/tasks/{task_id}/cancel` |
| GET | `/api/v3/workflows` |
| POST | `/api/v3/workflows/trigger` |
| GET | `/api/v3/workflows/{workflow_id}` |

## Providers, Models, and Routing

| Method | Path |
|---|---|
| GET | `/api/v3/providers` |
| POST | `/api/v3/providers` |
| GET | `/api/v3/providers/health` |
| POST | `/api/v3/providers/test` |
| GET | `/api/v3/providers/{provider_id}` |
| PUT | `/api/v3/providers/{provider_id}` |
| DELETE | `/api/v3/providers/{provider_id}` |
| GET | `/api/v3/models` |
| GET | `/api/v3/models/registry` |
| GET | `/api/v3/routing` |
| PUT | `/api/v3/routing` |
| GET | `/api/v3/routing/rules` |
| POST | `/api/v3/routing/rules` |

## Content Production & Creative Assets

| Method | Path |
|---|---|
| GET | `/api/v3/assets` |
| POST | `/api/v3/assets` |
| GET | `/api/v3/assets/{asset_id}` |
| GET | `/api/v3/reviews` |
| POST | `/api/v3/reviews` |
| GET | `/api/v3/reviews/{review_id}` |
| GET | `/api/v3/world` |
| POST | `/api/v3/world` |
| GET | `/api/v3/storyboard` |
| POST | `/api/v3/storyboard` |
| GET | `/api/v3/characters` |
| POST | `/api/v3/characters` |
| GET | `/api/v3/production` |
| POST | `/api/v3/production` |

## Conversations & Agents

| Method | Path |
|---|---|
| GET | `/api/v3/conversations` |
| POST | `/api/v3/conversations` |
| GET | `/api/v3/conversations/{conversation_id}` |
| GET | `/api/v3/conversations/{conversation_id}/agents` |
| GET | `/api/v3/conversations/{conversation_id}/tasks` |
| GET | `/api/v3/conversations/{conversation_id}/events` |
| GET | `/api/v3/agent-definitions` |
| POST | `/api/v3/agent-definitions` |
| GET | `/api/v3/agent-instances` |
| POST | `/api/v3/agent-instances` |

## Studio Runtime

| Method | Path |
|---|---|
| GET | `/api/v3/studio/capabilities` |
| GET | `/api/v3/studio/readiness` |
| GET | `/api/v3/studio/artifacts` |
| GET | `/api/v3/studio/artifacts/{artifact_id}` |
| POST | `/api/v3/studio/series` |
| GET | `/api/v3/studio/series` |
| GET | `/api/v3/studio/series/{series_id}` |
| POST | `/api/v3/studio/series/{series_id}/episodes` |
| GET | `/api/v3/studio/series/{series_id}/episodes` |
| GET | `/api/v3/studio/series/{series_id}/episodes/{episode_id}` |
| POST | `/api/v3/studio/episodes` |
| GET | `/api/v3/studio/episodes` |
| GET | `/api/v3/studio/episodes/{episode_id}` |
| POST | `/api/v3/studio/episodes/{episode_id}/idea-selection` |
| POST | `/api/v3/studio/episodes/{episode_id}/revisions` |
| POST | `/api/v3/studio/episodes/{episode_id}/approvals` |
| POST | `/api/v3/studio/episodes/{episode_id}/screenplay-lock` |
| POST | `/api/v3/studio/episodes/{episode_id}/runs` |
| GET | `/api/v3/studio/episodes/{episode_id}/runs/{run_id}` |
| GET | `/api/v3/studio/episodes/{episode_id}/runs/{run_id}/events` |
| POST | `/api/v3/studio/runs` |
| GET | `/api/v3/studio/runs/{run_id}` |
| GET | `/api/v3/studio/runs/{run_id}/events` |

## System, Dashboard, and Monitoring

| Method | Path |
|---|---|
| GET | `/api/v3/dashboard` |
| GET | `/api/v3/monitoring` |
| GET | `/api/v3/system` |
| GET | `/api/v3/settings` |
| GET | `/api/v3/browser` |
| GET | `/api/v3/memory` |
| GET | `/api/v3/files` |
| GET | `/api/v3/logs` |

## Retired Tombstones

| Path | Status | Response |
|---|---|---|
| `/api/v1/*` | `410 Gone` | `{"type": "https://windagent.io/errors/api-v1-removed", "status": 410, "available_endpoints": "/api/v3/*"}` |
| `/api/v2/*` | `410 Gone` | `{"type": "https://windagent.io/errors/api-v2-retired", "status": 410, "available_endpoints": "/api/v3/*"}` |

## Durability and process contract

The API process accepts work and persists state via domain repositories and Unit of Work. The Worker claims and executes durable work through bounded pipelines and fencing tokens. Both processes must use the same `WINDAGENT_DATABASE_URL`; in-memory state is not a production source of truth.

PostgreSQL is authoritative for multi-replica deployments. SQLite is supported for local single-process development.
