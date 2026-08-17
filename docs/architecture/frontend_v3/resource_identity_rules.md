# Resource Identity Rules & URI Formatting

This document establishes the prefix standards, identifier formats, and canonical URI structures across the WindAgent V3 architecture.

---

## 1. ID Prefix Standards

All entity primary keys in V3 must use lowercase type-prefixed nanoids or UUIDv7 strings:

| Entity Type | Prefix | Example ID | Generation Method |
|---|---|---|---|
| **Project** | `proj_` | `proj_01j7c3f8q9k2...` | UUIDv7 / Nanoid (16 char) |
| **Episode** | `ep_` | `ep_01j7c3f9...` | UUIDv7 / Nanoid (16 char) |
| **Character** | `char_` | `char_01j7c3fa...` | UUIDv7 / Nanoid (16 char) |
| **World Setting** | `world_` | `world_01j7c3fb...` | UUIDv7 / Nanoid (16 char) |
| **Asset** | `ast_` | `ast_01j7c3fc...` | UUIDv7 / Nanoid (16 char) |
| **Artifact** | `art_` | `art_01j7c3fd...` | UUIDv7 / SHA256-prefixed |
| **File** | `file_` | `file_01j7c3fe...` | UUIDv7 / Nanoid |
| **AgentDefinition** | `agdef_` | `agdef_screenwriter_01` | Semantic Slug or UUIDv7 |
| **AgentInstance** | `aginst_` | `aginst_01j7c3ff...` | UUIDv7 (Ephemeral) |
| **Task** | `tsk_` | `tsk_01j7c3ga...` | UUIDv7 |
| **Run** | `run_` | `run_01j7c3gb...` | UUIDv7 |
| **WorkflowDefinition** | `wfdef_` | `wfdef_studio_pipeline` | Semantic Slug or UUIDv7 |
| **WorkflowRun** | `wfrun_` | `wfrun_01j7c3gc...` | UUIDv7 |
| **Revision** | `rev_` | `rev_01j7c3gd...` | UUIDv7 / Git-like SHA |

---

## 2. Canonical REST URI Schemas

All Unified API V3 endpoints follow strict REST resource hierarchy:

```text
# Projects & Sub-resources
GET    /api/v3/projects
POST   /api/v3/projects
GET    /api/v3/projects/{project_id}
PATCH  /api/v3/projects/{project_id}
DELETE /api/v3/projects/{project_id}

GET    /api/v3/projects/{project_id}/episodes
POST   /api/v3/projects/{project_id}/episodes
GET    /api/v3/projects/{project_id}/episodes/{episode_id}
PATCH  /api/v3/projects/{project_id}/episodes/{episode_id}

GET    /api/v3/projects/{project_id}/characters
POST   /api/v3/projects/{project_id}/characters

# Assets & Artifacts
GET    /api/v3/assets
POST   /api/v3/assets
GET    /api/v3/assets/{asset_id}
GET    /api/v3/artifacts/{artifact_id}

# Agent Definitions & Instances
GET    /api/v3/agents/definitions
POST   /api/v3/agents/definitions
GET    /api/v3/agents/instances
POST   /api/v3/agents/instances/{instance_id}/execute

# Workflows & Tasks
GET    /api/v3/workflows/definitions
POST   /api/v3/workflows/runs
GET    /api/v3/workflows/runs/{workflow_run_id}
GET    /api/v3/workflows/runs/{workflow_run_id}/tasks/{task_id}
```

---

## 3. Serialization Invariants

1. **Timestamps**: All timestamps in request/response bodies must be formatted as ISO 8601 UTC strings (`YYYY-MM-DDTHH:MM:SS.sssZ`).
2. **Casing**: All JSON property keys must use `snake_case` in backend Python contracts and generated TypeScript contracts will map to typed properties according to codegen specifications.
3. **Nullability**: Optional fields default to `null`, never omitted if present in the schema definition.
