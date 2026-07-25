# Source-to-Target Mapping for V2 Canonical Schema

This document defines the mapping from legacy backend tables to V2 canonical schema tables.

## Overview

The migration consists of two phases:
1. **Phase 1 (migration_001)**: Create V2 canonical tables
2. **Phase 2 (migration_002)**: Migrate data from legacy backend tables to V2 tables

## Table Mappings

### 1. Session Tables

| Source Table | Target Table | Mapping Notes |
|--------------|--------------|---------------|
| `chat_sessions` (backend) | `chat_sessions` (V2) | Direct mapping, preserve all columns |
| `chat_sessions` (backend) | `v2_sessions` (storage) | Transform: id, title, status, created_at, updated_at |

**Field Mapping:**
- `id` → `id` (UUID)
- `title` → `title`
- `status` → `status` (enum validation)
- `agent_id` → (not mapped to V2)
- `workspace_root` → (not mapped to V2)
- `created_at` → `created_at`
- `updated_at` → `updated_at`
- `last_event_sequence` → `last_event_sequence`
- `metadata_json` → (not mapped to V2)

### 2. Task Tables

| Source Table | Target Table | Mapping Notes |
|--------------|--------------|---------------|
| `parent_tasks` (backend) | `v2_tasks` (storage) | Transform task hierarchy to flat tasks |
| `task_plans` (backend) | (not in V2) | Plan data stored differently in V2 |
| `task_nodes` (backend) | (not in V2) | Plan nodes stored differently in V2 |
| `task_edges` (backend) | (not in V2) | Plan edges stored differently in V2 |

**Field Mapping for parent_tasks → v2_tasks:**
- `id` → `id`
- `conversation_id` → `session_id`
- `title` → `prompt`
- `status` → `status`
- `label` → (tags)
- `progress` → (not mapped)
- `created_at` → `created_at`

### 3. Workflow Tables

| Source Table | Target Table | Mapping Notes |
|--------------|--------------|---------------|
| `workflows` (backend) | `v2_workflow_runs` (storage) | Rename and transform |
| `workflow_steps` (backend) | `v2_workflow_steps` (storage) | Direct mapping |

**Field Mapping for workflows → v2_workflow_runs:**
- `id` → `run_id`
- `session_id` → `session_id`
- `status` → `status`
- `created_at` → `created_at`
- `updated_at` → `updated_at`

**Field Mapping for workflow_steps → v2_workflow_steps:**
- `id` → `id`
- `workflow_id` → `run_id`
- `step_type` → (not mapped, use name)
- `name` → `name`
- `tool_name` → `tool_name`
- `params_json` → `params_json`
- `status` → `status`
- `order_index` → `step_order`

### 4. Execution Events

| Source Table | Target Table | Mapping Notes |
|--------------|--------------|---------------|
| `execution_events` (backend) | `execution_events` (storage) | Direct mapping, preserve all |

**Field Mapping:**
- `id` → `id`
- `session_id` → `session_id`
- `event_type` → `event_type`
- `data_json` → `data_json`
- `event_seq` → `event_seq`
- `created_at` → `created_at`

### 5. Tool Calls

| Source Table | Target Table | Mapping Notes |
|--------------|--------------|---------------|
| `tool_calls` (backend) | (not in V2 storage) | Tool calls are execution artifacts, not persisted |

### 6. Artifacts

| Source Table | Target Table | Mapping Notes |
|--------------|--------------|---------------|
| `task_artifacts` (backend) | `v2_artifacts` (storage) | Direct mapping |

**Field Mapping:**
- `id` → `id`
- `task_id` → (not mapped, use session_id reference)
- `agent_instance_id` → (not mapped)
- `artifact_type` → `artifact_type`
- `path_or_uri` → `uri`
- `metadata_json` → `metadata_json`
- `checksum` → `checksum`
- `created_at` → `created_at`

### 7. Provider Models

| Source Table | Target Table | Mapping Notes |
|--------------|--------------|---------------|
| `model_providers` (backend) | `v2_provider_configs` (storage) | Transform to provider configs |
| `model_catalog` (backend) | (not in V2, use canonical_models from V3) | See V3 models |
| `canonical_models` (backend) | (see V3 canonical_models) | Already in V3 schema |
| `provider_model_bindings` (backend) | (see V3 bindings) | Already in V3 schema |

**Note:** V3 schema already has comprehensive provider/model tables in `v3_models.py`.
These will be used instead of creating new V2 provider tables.

### 8. Route Locks and Attempts

| Source Table | Target Table | Mapping Notes |
|--------------|--------------|---------------|
| `route_locks` (backend) | (see V3 RouteLockV3ORM) | V3 schema |
| `route_attempts` (backend) | (see V3 RouteAttemptORM) | V3 schema |
| `model_routing_rules` (backend) | (not in V2 storage) | Routing is orchestration concern |

### 9. Agent Registry (Legacy)

| Source Table | Target Table | Mapping Notes |
|--------------|--------------|---------------|
| `agents` (backend) | (not in V2 storage) | Agents are orchestration concern |
| `agent_sessions` (backend) | (not in V2 storage) | Sessions are runtime concern |
| `agent_instances` (backend) | (not in V2 storage) | Runtime concern |
| `agent_runs` (backend) | (not in V2 storage) | Runtime concern |

### 10. Permissions

| Source Table | Target Table | Mapping Notes |
|--------------|--------------|---------------|
| `permission_requests` (backend) | (not in V2 storage) | Permissions are security concern |

### 11. Model Runtime Status

| Source Table | Target Table | Mapping Notes |
|--------------|--------------|---------------|
| `model_runtime_status` (backend) | (not in V2 storage) | Runtime monitoring, not persisted |
| `provider_quota_snapshots` (backend) | (not in V2 storage) | Runtime monitoring |
| `model_activity` (backend) | (not in V2 storage) | Runtime monitoring |
| `model_benchmark_runs` (backend) | (not in V2 storage) | Runtime monitoring |
| `router_execution_logs` (backend) | (not in V2 storage) | Runtime monitoring |

### 12. Outbox

| Source Table | Target Table | Mapping Notes |
|--------------|--------------|---------------|
| (none) | `v2_outbox_records` (storage) | New in V2, no legacy source |

## Data Preservation Requirements

All migrations must preserve:
1. **Row count** - Same number of rows after migration
2. **IDs** - All primary keys preserved
3. **Relationships** - Foreign key relationships maintained
4. **Timestamps** - created_at, updated_at preserved
5. **Status** - Status values mapped correctly
6. **Payload hashes** - JSON data integrity verified
7. **Audit history** - All historical data preserved

## Migration Order

1. Create V2 tables (migration_001)
2. Create migration history table (migration_001)
3. Backup existing database (before migration_002)
4. Migrate data from legacy tables (migration_002)
5. Verify data integrity (migration_002)
6. Create indexes (migration_002)

## Rollback Strategy

Each migration has a corresponding downgrade:
- migration_001 downgrade: Drop V2 tables
- migration_002 downgrade: Restore from backup (no data loss)
