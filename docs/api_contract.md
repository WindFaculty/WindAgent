# WindAgent Architecture V2 API contract

## Authority and versioning

`windagent_api.main:app` is the only ASGI application authority.

- Canonical resources use `/api/v2/*`.
- Every `/api/v1/*` request returns `410 Gone`.
- Health endpoints remain unversioned so orchestrators can probe them without
  binding to a business API version.

The V1 tombstone body includes `status: 410`, a migration guide, and
`available_endpoints: "/api/v2/*"`.

## Health

| Method | Path | Purpose |
|---|---|---|
| GET | `/health/live` | Process liveness |
| GET | `/health/ready` | Dependency-aware readiness |

## Sessions

| Method | Path |
|---|---|
| POST | `/api/v2/sessions` |
| GET | `/api/v2/sessions` |
| GET | `/api/v2/sessions/{session_id}` |
| GET | `/api/v2/sessions/{session_id}/snapshot` |
| GET | `/api/v2/sessions/{session_id}/events` |
| GET | `/api/v2/sessions/{session_id}/messages` |
| POST | `/api/v2/sessions/{session_id}/messages` |
| POST | `/api/v2/sessions/{session_id}/cancel` |
| POST | `/api/v2/sessions/{session_id}/archive` |
| DELETE | `/api/v2/sessions/{session_id}` |

## Tasks and runs

| Method | Path |
|---|---|
| POST | `/api/v2/tasks` |
| GET | `/api/v2/tasks` |
| GET | `/api/v2/tasks/{task_id}` |
| POST | `/api/v2/tasks/{task_id}/cancel` |
| GET | `/api/v2/runs` |
| GET | `/api/v2/runs/{run_id}` |

## Events

| Method | Path | Transport |
|---|---|---|
| GET | `/api/v2/events` | JSON |
| GET | `/api/v2/events/stream` | Server-sent events |
| WS | `/api/v2/events/ws` | WebSocket |

Event payloads follow the canonical envelope in
[`docs/event_protocol.md`](event_protocol.md).

## Registries and catalogs

| Method | Path |
|---|---|
| GET | `/api/v2/providers` |
| GET | `/api/v2/providers/health` |
| GET | `/api/v2/tools` |
| GET | `/api/v2/workflows` |
| POST | `/api/v2/workflows/trigger` |
| GET | `/api/v2/plugins` |
| GET | `/api/v2/skills` |
| GET | `/api/v2/artifacts` |
| GET | `/api/v2/memory` |

## Permissions, evaluation, and observability

| Method | Path |
|---|---|
| GET | `/api/v2/permissions` |
| POST | `/api/v2/permissions/evaluate` |
| GET | `/api/v2/evals` |
| GET | `/api/v2/evals/reports` |
| GET | `/api/v2/observability/spans` |

## Durability and process contract

The API process accepts work and persists state. The Worker claims and executes
durable work. Both processes must use the same `WINDAGENT_DATABASE_URL`;
in-memory state is not a production source of truth.

PostgreSQL is authoritative for multi-replica deployments. SQLite is supported
for local single-process development.
