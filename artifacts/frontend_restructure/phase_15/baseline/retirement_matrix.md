# API V2 Retirement Matrix — Baseline

| Endpoint Prefix | Backend Router | Frontend Consumer Count | V3 Canonical Replacement | Retirement Status | Classification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/api/v2/sessions` | `v2_sessions_router` | 0 | `/api/v3/conversations` | RETIRED | REMOVE |
| `/api/v2/tasks` | `v2_tasks_router` | 0 | `/api/v3/tasks` | RETIRED | REMOVE |
| `/api/v2/runs` | `v2_runs_router` | 0 | `/api/v3/tasks` | RETIRED | REMOVE |
| `/api/v2/workflows` | `v2_workflows_router` | 0 | `/api/v3/workflows` | RETIRED | REMOVE |
| `/api/v2/events` | `v2_events_router` | 0 | `/api/v3/system/events` | RETIRED | REMOVE |
| `/api/v2/providers` | `v2_providers_router` | 0 | `/api/v3/providers` | RETIRED | REMOVE |
| `/api/v2/tools` | `v2_tools_router` | 0 | `/api/v3/agents/tools` | RETIRED | REMOVE |
| `/api/v2/permissions` | `v2_permissions_router` | 0 | `/api/v3/settings` | RETIRED | REMOVE |
| `/api/v2/artifacts` | `v2_artifacts_router` | 0 | `/api/v3/assets` | RETIRED | REMOVE |
| `/api/v2/memory` | `v2_memory_router` | 0 | `/api/v3/memory` | RETIRED | REMOVE |
| `/api/v2/plugins` | `v2_plugins_router` | 0 | `/api/v3/agents` | RETIRED | REMOVE |
| `/api/v2/skills` | `v2_skills_router` | 0 | `/api/v3/agents/skills` | RETIRED | REMOVE |
| `/api/v2/evals` | `v2_evals_router` | 0 | `/api/v3/monitoring` | RETIRED | REMOVE |
| `/api/v2/observability` | `v2_observability_router` | 0 | `/api/v3/monitoring` | RETIRED | REMOVE |
| `/api/v2/browser` | `v2_browser_router` | 0 | `/api/v3/browser` | RETIRED | REMOVE |
| `/api/v2/video-production` | `v2_production_workspace_router` | 0 | `/api/v3/production` | RETIRED | REMOVE |
| `/api/v2/screenplay` | `v2_screenplay_workspace_router` | 0 | `/api/v3/episodes` | RETIRED | REMOVE |
| `/api/v2/video-production/assets` | `v2_assets_router` | 0 | `/api/v3/assets` | RETIRED | REMOVE |
| `/api/v2/collaboration` | `v2_collaboration_router` | 0 | `/api/v3/reviews` | RETIRED | REMOVE |
| `/api/v2/conversations` | `v2_conversations_router` | 0 | `/api/v3/conversations` | RETIRED | REMOVE |
| `/api/v2/recovery` | `v2_conflict_recovery_router` | 0 | `/api/v3/episodes` | RETIRED | REMOVE |
