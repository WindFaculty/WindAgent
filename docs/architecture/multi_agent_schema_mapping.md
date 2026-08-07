# Multi-Agent Workspace — Schema Mapping (V2 → Target)

> Phụ lục A của **ADR 0006** (`docs/adr/0006-multi-agent-workspace-aggregates.md`).
> Mục tiêu: map từng bảng storage hiện tại (V2/V3) sang schema multi-agent đích,
> làm baseline cho migration (Phase 1 — G1.1/G1.2/G1.3) và không làm mất dữ liệu cần giữ.

## 1. Nguyên tắc

- **Giữ nguyên** các bảng provider/routing V3 — chúng đã đúng thiết kế (RouteLock đã có
  unique active per scope, credential đã có `secret_ciphertext`). Chỉ chuẩn hóa tên + thêm
  FK/index khi cần.
- **Chuyển đổi có kiểm chứng** các bảng V2: `chat_sessions` → `conversations`,
  `v2_tasks`/`v2_workflow_*` → `parent_tasks` + immutable `task_plan_versions`.
- **Bổ sung mới** các bảng aggregate chưa tồn tại: `agent_instances`, `agent_sessions`,
  `task_node_runs`, `tool_executions`, `worktrees`.
- Mọi migration đi qua **Alembic** (Phase 1 thay `create_all`), có upgrade/downgrade rehearsal
  trên bản copy (đã có tiền lệ `tests/unit/storage/migrations/`).

## 2. Mapping chi tiết

### 2.1 Conversation & parent task

| Bảng V2 hiện tại | Cột chuyển | Bảng đích | Ghi chú |
| :--- | :--- | :--- | :--- |
| `chat_sessions` (`SessionORM`) | `id` → `conversation_id`; `title`; `status`; `created_at`/`updated_at` | **`conversations`** | Aggregate #1 Conversation. `metadata_json` → `metadata_json`. `agent_id`/`workspace_root` **không** chuyển (thuộc AgentInstance/Worktree). |
| `v2_tasks` (`TaskORM`) | `id` → `parent_task_id`; `prompt` → `objective`; `session_id` → `conversation_id` (FK) | **`parent_tasks`** | Aggregate #2 ParentTask. `status` giữ nguyên chuẩn hóa sang canonical state. Thêm `active_plan_version_id` (FK → task_plan_versions). |
| `v2_workflow_runs`/`v2_workflow_runs_v2` | `run_id`/`workflow_id` → `plan_version_id`; `definition_json` → `dag_json` | **`task_plan_versions`** | Aggregate #5 TaskPlanVersion (immutable). `version` int tăng dần; thêm `parent_task_id` FK; `created_at`; không mutation in-place. |
| `v2_workflow_steps` + `workflow_edges` | `id` → `node_id`; `step_order` → `position`; `tool_name`/`params_json`; `source/target` → `from_node_id`/`to_node_id` | **`task_nodes`** + **`task_edges`** | Node/edge của một `plan_version_id`. Đảm bảo DAG validate khi tạo version mới. |
| `task_runs` (`TaskRunORM`) + `workflow_step_runs` | `id` → `task_node_run_id`; `state`; `facts_json`; `step_run_id`/`workflow_run_id` → `plan_version_id`+`node_id` | **`task_node_runs`** | Aggregate #6 TaskNodeRun. Persist `node_state`, `dependency_state`, `retry_state`, `routing_snapshot_json`, `concurrency_group`, `next_retry_at`. |

### 2.2 Agent instance & session

| Bảng V2 hiện tại | Cột chuyển | Bảng đích | Ghi chú |
| :--- | :--- | :--- | :--- |
| (không có — chỉ tồn tại trong backend V2 models, chưa canon) | — | **`agent_instances`** | Aggregate #3 AgentInstance: `agent_instance_id` PK, `parent_task_id` FK, `agent_type`, `permission_profile`, `canonical_model_id`, `status`, `assigned_node_id`. |
| (không có — tương tự) | — | **`agent_sessions`** | Aggregate #4 AgentSession: `agent_session_id` PK, `agent_instance_id` FK, **`windagent_session_id` UNIQUE**, `runtime_locator`/`hermes_run_id`, `status` + `version` (CAS), `created_at`/`updated_at`. |

### 2.3 Route lock, tool execution, worktree

| Bảng V2/V3 hiện tại | Cột chuyển | Bảng đích | Ghi chú |
| :--- | :--- | :--- | :--- |
| `route_locks_v3` (`RouteLockV3ORM`) | giữ nguyên; đổi `scope_type` enum → `conversation|parent_task|agent_session` | **`route_locks`** | Aggregate #7 RouteLock. Đã có unique active per scope + version CAS. Chuẩn hóa scope. |
| `route_attempts_v3` + `provider_routing_audit_v3` | giữ nguyên | **`route_attempts`** + **`provider_routing_audit`** | G2.2 failover audit; mỗi attempt gắn `route_lock_id` + `turn_id`. |
| `execution_leases` (`ExecutionLeaseORM`) | `idempotency_key` unique đã có; tách phần tool | **`tool_executions`** + giữ **`execution_leases`** | Aggregate #8 ToolExecution: `tool_execution_id` PK, `idempotency_key` UNIQUE, `tool_name`, `arguments_redacted`, `status`, `result_ref`, `claimant`. Lease giữ cho concurrency_group/worktree lock. |
| (không có) | — | **`worktrees`** | Aggregate #9 Worktree: `worktree_id` PK, `agent_instance_id` FK, `path`, `branch`, `status` (active/quarantined/removed), `repo_root`, `created_at`. |

### 2.4 Provider/routing (giữ nguyên, chuẩn hóa tên)

| Bảng hiện tại | Quyết định |
| :--- | :--- |
| `provider_vendors`, `provider_credentials`, `provider_endpoints`, `canonical_models_v3`, `endpoint_model_bindings`, `model_routing_rules_v3` | **Giữ nguyên**. `provider_credentials.secret_ciphertext` đã đúng hướng (G2.3 — thay fallback key cố định bằng AES-GCM/KMS). |
| `endpoint_runtime_state`, `endpoint_health_samples`, `endpoint_rate_limit_windows`, `provider_quota_snapshots_v3`, `provider_usage_ledger`, `model_discovery_snapshots`, `response_cache_entries` | **Giữ nguyên**. |
| `v2_provider_configs` (`ProviderConfigORM`) | **Deprecate** → migrate sang `provider_credentials`/`provider_endpoints` V3. |

### 2.5 Events, outbox, artifacts, misc

| Bảng hiện tại | Cột chuyển | Bảng đích | Ghi chú |
| :--- | :--- | :--- | :--- |
| `execution_events` (`ExecutionEventORM`) | `session_id` → `conversation_id`; thêm `agent_instance_id`, `sequence` (monotonic per conversation), `event_id` | **`conversation_events`** | G6.1/G6.2 — envelope bắt buộc `conversation_id`/`agent_instance_id`/`agent_session_id`/`sequence`/`event_id`. |
| `v2_outbox_records` | giữ nguyên (đã có dedup key + claim) | **`outbox_records`** | Không đổi ngữ nghĩa. |
| `v2_artifacts` (`ArtifactRefORM`) | giữ; thêm `agent_instance_id`/`task_node_run_id` optional | **`artifacts`** | G6.3 PartialArtifact: `visibility=audit_only` cột mới. |
| `recovery_leader_leases`, `worker_registrations`, `cancellation_requests`, `workflow_checkpoints`, `execution_attempts`, `memory_records`, `plugin_installations`, `skill_installations`, `task_execution_results_v2`, `v2_outbox_replay_audit` | giữ nguyên / map tên | giữ nguyên | Không đổi ngữ nghĩa; chỉ chuẩn hóa tên bảng. |

## 3. Bảng tóm tắt 9 aggregate ↔ bảng đích

| Aggregate | Bảng đích | Nguồn hiện tại |
| :--- | :--- | :--- |
| Conversation | `conversations` | `chat_sessions` |
| ParentTask | `parent_tasks` | `v2_tasks` |
| AgentInstance | `agent_instances` | (mới) |
| AgentSession | `agent_sessions` | (mới) |
| TaskPlanVersion | `task_plan_versions` | `v2_workflow_runs_v2` + `v2_workflow_steps` |
| TaskNodeRun | `task_node_runs` | `task_runs` + `workflow_step_runs` |
| RouteLock | `route_locks` | `route_locks_v3` |
| ToolExecution | `tool_executions` | `execution_leases` (tách) |
| Worktree | `worktrees` | (mới) |

## 4. Ràng buộc migration (Phase 1 exit gates)

1. `alembic upgrade head` tạo DB mới hoàn chỉnh (thay `create_all`).
2. `alembic downgrade base` hoạt động trên DB test.
3. Upgrade từ DB V2 fixture (có `chat_sessions`/`v2_tasks` seed) **không mất dữ liệu cần giữ**
   (title, status, metadata, objective).
4. `agent_sessions.windagent_session_id` UNIQUE; `parent_tasks.conversation_id` FK+index;
   `agent_instances.conversation_id` FK+index.
5. `route_locks` unique active theo scope; `tool_executions.idempotency_key` UNIQUE.
6. State mutation dùng CAS/version (đã có cột `version` ở `route_locks_v3`, `task_runs`).

### 4.1 Trạng thái triển khai (Phase 1 hoàn tất)

| Gate | Trạng thái | Nơi triển khai |
| :--- | :--- | :--- |
| 1. `alembic upgrade head` | ✅ | `storage/windagent_storage/migrations/alembic/` (`0001_baseline`, `0002_legacy_v2_data`, `0003_multi_agent_canonical`) + `migrations/runner.py`; runtime `DatabaseManager.upgrade_to_head()` thay `create_tables` ở API/Worker/CLI composition |
| 2. `alembic downgrade base` | ✅ | `runner.alembic_downgrade_base()` (test DB) |
| 3. Upgrade V2 fixture không mất dữ liệu | ✅ | Data lane `0002` (legacy→V2) + `0003` (V2→multi-agent), kiểm chứng bởi `tests/unit/storage/migrations/test_phase1_migration_integrity.py` |
| 4. UNIQUE `windagent_session_id`, FK+index conversation | ✅ | `0003` — `uq_agent_sessions_windagent_session_id`, `ix_parent_tasks_conversation_id`, `ix_agent_instances_conversation_id` |
| 5. `tool_executions.idempotency_key` UNIQUE | ✅ | `0003` — `uq_tool_executions_idempotency_key` (route lock active-per-scope đã có sẵn ở `route_locks_v3`) |
| 6. CAS/version | ✅ | `agent_sessions.version`, `task_node_runs.version` (thêm mới) + `route_locks_v3.version`/`task_runs.version` (đã có) |

G2.3 (mã hóa secret) / G9.3 (WAL async) / G9.4 (redact_before_persist) / G9.5 (workspace_root)
cũng đã hoàn tất trong Phase 1 — chi tiết ở `tests/unit/storage/migrations/test_phase1_migration_integrity.py`
và các exit-gate test tương ứng.
