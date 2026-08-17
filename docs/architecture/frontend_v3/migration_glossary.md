# Migration Glossary: V2 Legacy to V3 Canonical

This glossary serves as the translation guide for engineering teams migrating legacy V2 code, handwritten clients, and old DTOs to the Unified V3 architecture.

---

## 1. Terminology Translation Matrix

| Legacy Concept (V2) | Canonical Concept (V3) | Migration Rule | Affected Files / Routers |
|---|---|---|---|
| `Series` / `StudioSeries` | `Project` | Treat `Series` as legacy alias; forward to `Project` aggregate. | `v2_production_workspace.py`, `StudioStore.ts`, `routers/v3/studio` |
| `series_id` | `project_id` (alias accepted) | New endpoints require `project_id`. Legacy query param `series_id` aliased in gateway. | `client.ts`, `StudioPage.tsx` |
| `Agent` (template) | `AgentDefinition` | Refactor DTOs to use `AgentDefinition` and `agdef_` IDs. | `v2_agents.py`, `Agents.tsx`, `multiAgentStore.ts` |
| `Agent` (runtime worker) | `AgentInstance` | Rename runtime worker structures to `AgentInstance`. | `MultiAgentWorkspace.tsx`, `v2_sessions.py` |
| `v2_files` (JSON outputs) | `Artifact` | Structured outputs moved to `art_*` artifact storage. | `v2_artifacts.py`, `Files.tsx` |
| `v2_files` (raw uploads) | `File` | Generic uploads stay under `file_*` workspace files. | `v2_browser.py`, `Files.tsx` |
| `v2_assets` | `Asset` | Refactor to cataloged asset registry with versioning. | `v2_assets.py`, `AssetWorkspace.tsx` |
| `Run` (unscoped) | `Task` / `Run` / `WorkflowRun` | Scope to execution DAG level (`tsk_`, `run_`, `wfrun_`). | `v2_runs.py`, `v2_tasks.py`, `v2_workflows.py` |
| `Database` (sidebar) | `Memory` | Rename sidebar label and routing hash to `Memory`. | `DESKTOP_NAVIGATION_GROUPS`, `App.tsx`, `Memory.tsx` |
| `ETag` / `If-Match` | `version` / `expected_version` | Migrate optimistic locking to explicit payload `expected_version`. | All mutating V3 routes |

---

## 2. API Route Translation Map

| Legacy V2 Endpoint | Canonical V3 Endpoint | Status in Phase 1–5 |
|---|---|---|
| `/api/v2/providers` | `/api/v3/providers` | Coexistence (V2 kept, V3 added in P2) |
| `/api/v2/agents` | `/api/v3/agents/definitions` | Coexistence |
| `/api/v2/sessions` | `/api/v3/sessions` | Coexistence |
| `/api/v2/tasks` | `/api/v3/workflows/runs` | Coexistence |
| `/api/v2/memory` | `/api/v3/memory` | Coexistence |
| `/api/v2/assets` | `/api/v3/assets` | Coexistence |
| `/api/v2/production_workspace` | `/api/v3/projects` | Coexistence |
| `/api/v3/studio/series` | `/api/v3/projects` (with studio facade) | Facade maintained |

---

## 3. Deprecation and Decommissioning Schedule

- **Phase 0–5 (Foundation)**: Zero removal of V2 endpoints; compatibility aliases active.
- **Phase 6–13 (Slice Migration)**: Vertical slices migrate one by one from V2 to V3.
- **Phase 14–16 (Legacy Decommission)**: Deprecation warnings emitted, legacy V2 endpoints sunset.
