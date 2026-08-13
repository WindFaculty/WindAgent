# WindAgent Architecture V2 API contract

## Authority and versioning

`windagent_api.main:app` is the only ASGI application authority.

- Canonical resources use `/api/v2/*` (business API).
- Studio runtime uses `/api/v3/studio/*`.
- Every `/api/v1/*` request returns `410 Gone` (tombstone with migration guide
  and `available_endpoints: "/api/v2/*"`).
- Health endpoints remain unversioned so orchestrators can probe them without
  binding to a business API version.

Source of truth for this table: router registration in
`apps/api/windagent_api/main.py` + `apps/api/windagent_api/routers/`.
If the table drifts, regenerate from the routers.

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
| GET | `/api/v2/sessions/validate-workspace-root` |
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

## Workflows

| Method | Path |
|---|---|
| GET | `/api/v2/workflows` |
| POST | `/api/v2/workflows/trigger` |

## Events

| Method | Path | Transport |
|---|---|---|
| GET | `/api/v2/events` | JSON |
| GET | `/api/v2/events/stream` | Server-sent events |
| WS | `/api/v2/events/ws` | WebSocket |
| GET | `/api/v2/video-production/events` | JSON (legacy production events) |

Event payloads follow the canonical `EventEnvelope` in
[`docs/event_protocol.md`](event_protocol.md).

## Registries and catalogs

| Method | Path |
|---|---|
| GET | `/api/v2/providers` |
| GET | `/api/v2/providers/health` |
| GET | `/api/v2/tools` |
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

## Browser automation

| Method | Path |
|---|---|
| GET | `/api/v2/browser/sessions/{session_id}` |
| DELETE | `/api/v2/browser/sessions/{session_id}` |
| GET | `/api/v2/browser/sessions/{session_id}/screenshot` |
| POST | `/api/v2/browser/sessions/{session_id}/navigate` |
| POST | `/api/v2/browser/sessions/{session_id}/click` |
| POST | `/api/v2/browser/sessions/{session_id}/type` |
| POST | `/api/v2/browser/sessions/{session_id}/scroll` |
| POST | `/api/v2/browser/sessions/{session_id}/back` |
| POST | `/api/v2/browser/sessions/{session_id}/forward` |
| POST | `/api/v2/browser/sessions/{session_id}/reload` |
| POST | `/api/v2/browser/sessions/{session_id}/control` |

## Conversations and collaboration

| Method | Path |
|---|---|
| WS | `/ws/conversations/{conversation_id}` |
| GET | `/api/v2/conversations/{conversation_id}/agents` |
| POST | `/api/v2/conversations/{conversation_id}/agents/{agent_instance_id}/turns` |
| POST | `/api/v2/conversations/{conversation_id}/agents/{agent_instance_id}/stop` |
| POST | `/api/v2/conversations/{conversation_id}/agents/{agent_instance_id}/node-completion` |
| POST | `/api/v2/conversations/{conversation_id}/goals` |
| GET | `/api/v2/conversations/{conversation_id}/task-graphs` |
| GET | `/api/v2/conversations/{conversation_id}/routing/turns` |
| GET | `/api/v2/conversations/{conversation_id}/routing/turns/{turn_id}` |
| GET | `/api/v2/conversations/{conversation_id}/parent-tasks/{parent_task_id}/plan-versions` |
| POST | `/api/v2/conversations/{conversation_id}/parent-tasks/{parent_task_id}/plan-revisions` |
| GET | `/api/v2/collaboration/proposals` |
| POST | `/api/v2/collaboration/proposals` |
| GET | `/api/v2/collaboration/proposals/{proposal_id}` |
| POST | `/api/v2/collaboration/proposals/{proposal_id}/approve` |
| POST | `/api/v2/collaboration/proposals/{proposal_id}/reject` |
| GET | `/api/v2/collaboration/timeline` |
| POST | `/api/v2/collaboration/timeline/replay` |

## Conflict recovery

| Method | Path |
|---|---|
| POST | `/api/v2/conflict/check-stale-edit` |
| POST | `/api/v2/conflict/three-way-diff` |
| POST | `/api/v2/conflict/resolve` |
| GET | `/api/v2/recovery/reconcile` |

## Screenplay workspace

| Method | Path |
|---|---|
| POST | `/api/v2/screenplay/parse` |
| POST | `/api/v2/screenplay/serialize` |
| POST | `/api/v2/screenplay/impact/dry-run` |
| POST | `/api/v2/screenplay/proposals` |
| POST | `/api/v2/screenplay/revisions/compare` |
| POST | `/api/v2/screenplay/revisions/{revision_id}/lock` |
| GET | `/api/v2/screenplay/projects/{project_id}/read-model` |

## Video production workspace

| Method | Path |
|---|---|
| POST | `/api/v2/video-production/commands` |
| POST | `/api/v2/video-production/workspace/commands` |
| GET | `/api/v2/video-production/workspace/snapshot` |
| GET | `/api/v2/video-production/workspace/media/{media_token}` |
| GET | `/api/v2/video-production/projects/{project_id}` |
| GET | `/api/v2/video-production/projects/{project_id}/workspace` |
| GET | `/api/v2/video-production/assets` |
| GET | `/api/v2/video-production/assets/{asset_id}` |
| POST | `/api/v2/video-production/assets/commands` |
| POST | `/api/v2/video-production/assets/{asset_id}/compare` |
| GET | `/api/v2/video-production/assets/{asset_id}/provenance` |
| GET | `/api/v2/video-production/assets/{asset_id}/dependencies` |
| GET | `/api/v2/video-production/assets/{asset_id}/revisions` |
| GET | `/api/v2/video-production/assets/{asset_id}/artifacts/{artifact_key}` |

## Studio runtime (v3)

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

## Durability and process contract

The API process accepts work and persists state. The Worker claims and executes
durable work. Both processes must use the same `WINDAGENT_DATABASE_URL`;
in-memory state is not a production source of truth.

PostgreSQL is authoritative for multi-replica deployments. SQLite is supported
for local single-process development.
