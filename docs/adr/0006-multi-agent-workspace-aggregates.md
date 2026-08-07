# ADR 0006: Multi-Agent Workspace Target Architecture — Aggregates, Single Production Path, UI Decision

## Status

Accepted

## Context

WindAgent hiện phát triển **hai UI workspace song song** và **hai API contract mâu thuẫn** cho cùng một khái niệm "workspace", dẫn tới chi phí bảo trì kép, logic orchestration không được nối vào đường chạy thật, và rủi ro tích lũy technical debt trước khi phát hành.

Bằng chứng (audit `audit_report/AUDIT_agent_workspace_orchestration.md`, Phase 1):

- **UI 1 — `AgentWorkspacePage`** (`apps/desktop/src/pages/AgentWorkspace/AgentWorkspacePage.tsx`): session-based, dùng `agentSessionStore`, mount trực tiếp trong `App.tsx` tab "workspace". Dựa trên contract `/api/v2/sessions/*` (per-session).
- **UI 2 — `MultiAgentWorkspace`** (`apps/desktop/src/pages/MultiAgentWorkspace.tsx`): conversation-based, dùng `multiAgentStore`, **chưa được mount ở đâu trong App.tsx** (chỉ còn export). Dựa trên contract conversation/task-graph (các hàm `fetchConversationAgents`, `fetchConversationTasks`, `updateTaskNode`, `createTaskEdge`... đều trả `v2Unavailable`).
- **Các subsystem orchestration đã viết nhưng chưa có caller production**: `supervisor.ensure_orchestrator`/`spawn_subagent`, `dag_scheduler.run_plan`, `route_lock_service.acquire_lock`, `worktree_service`, `partial_audit.save_partial_artifact` — chỉ được gọi từ test (0 live callers).
- **Schema storage**: hai hệ ORM V2 (`chat_sessions`, `v2_tasks`, `v2_workflow_runs`, `task_runs`, `execution_leases`, `workflow_checkpoints`...) + V3 (`route_locks_v3`, `provider_credentials`...) còn rời rạc, `create_all` không có versioned migration (chưa có Alembic; có `migration_registry` custom).

Các ADR trước đã chốt nền tảng: model pinning 3 tầng (ADR 0001), task DAG + versioning (ADR 0002), WS durable events + replay (ADR 0003), git worktree isolation (ADR 0004), browser subprocess (ADR 0005). ADR này chốt **kiến trúc đích tổng thể** làm baseline cho toàn bộ roadmap G1.1–G9.7.

## Decision

### 1. Aggregate chính (canonical)

Mọi dữ liệu production của workspace được tổ chức quanh **9 aggregate** sau. Aggregate = đơn vị toàn vẹn + nguồn sự thật cho một vòng đời độc lập; mọi state mutation qua aggregate (CAS/version), mọi event gắn `aggregate_id` + `aggregate_type`.

| # | Aggregate | Định nghĩa | Định danh | Vòng đời |
|---|-----------|-----------|-----------|----------|
| 1 | **Conversation** | Phiên hội thoại cấp cao nhất giữa user và hệ thống; root của mọi thứ. WS/API entry. | `conversation_id` (UUID) | Tạo khi user mở hội thoại; tồn tại dài hạn; sở hữu ParentTasks + route lock scope. |
| 2 | **ParentTask** | Mục tiêu cụ thể của user trong một conversation; root của một lần "chạy kế hoạch". | `parent_task_id` (UUID) | Tạo khi Orchestrator nhận mục tiêu; sở hữu TaskPlanVersion + AgentInstances. |
| 3 | **AgentInstance** | Một sub-agent được spawn (coder/browser/research/orchestrator); unit độc lập để stop/cancel theo `agent_instance_id`. | `agent_instance_id` (UUID) | Tạo khi Orchestrator spawn; kết thúc khi task gán cho nó terminal. |
| 4 | **AgentSession** | Runtime session của một AgentInstance với provider/Hermes; `windagent_session_id` **unique** (ràng buộc DB). | `agent_session_id` (UUID) | Tạo khi spawn runtime; nhiều session có thể nối tiếp trong đời AgentInstance (reattach). |
| 5 | **TaskPlanVersion** | Một phiên bản **immutable** của task plan (DAG nodes + edges). Mỗi edit tạo version mới; run đang chạy pin vào version cũ. | `plan_version_id` (UUID) + `version` (int) | Tạo khi plan sinh/edited; không bao giờ mutate in-place. |
| 6 | **TaskNodeRun** | Một lần thực thi của một node trong một TaskPlanVersion; nắm trạng thái node, retry, routing_snapshot, kết quả. | `task_node_run_id` (UUID) | Tạo khi node chuyển ready→running; terminal khi completed/failed/cancelled. |
| 7 | **RouteLock** | Khóa routing 3 tầng (conversation / parent_task / agent_session) ghim canonical model + policy version + binding. Active theo scope **unique**. | `route_lock_id` (opaque) | Acquire trước mỗi turn; release khi scope terminal. |
| 8 | **ToolExecution** | Một lần thực thi tool với **idempotency key unique** — chỉ claimant đầu tiên chạy; retry đọc kết quả đã có. | `tool_execution_id` (UUID) + `idempotency_key` (unique) | Reserve trước side effect; complete/failed sau khi runtime trả kết quả. |
| 9 | **Worktree** | Git worktree/branch isolation của một coding agent; workspace_root lấy từ service, không nhận tùy ý từ client. | `worktree_id` (UUID) + path/branch | Tạo khi spawn coding agent; quarantine/remove khi cancel/boot reconcile. |

Quan hệ chính:

```text
Conversation 1──N ParentTask 1──N TaskPlanVersion 1──N TaskNodeRun
ParentTask 1──N AgentInstance 1──N AgentSession
RouteLock (scope: conversation | parent_task | agent_session)
TaskNodeRun N──1 ToolExecution (idempotent)
AgentInstance (coding) 1──1 Worktree
```

### 2. Một đường chạy production duy nhất

Chốt **single production path** sau — mọi request từ UI đi đúng tuyến này, không có nhánh song song (đặc biệt: không cho frontend tự chọn agent role tạo session runtime):

```text
Conversation WS/API (/ws/conversations/{id}, /api/v2/conversations/*)
  → OrchestratorService (entry duy nhất; tạo/reuse orchestrator session)
  → ParentTask + immutable TaskPlanVersion (DAG)
  → spawn AgentInstance + AgentSession + AgentRun per node
  → RouteLock acquire (conversation/parent_task/agent_session scope) + provider execution
  → worker/runtime/tool (Hermes / subprocess / browser)
  → durable events (persist-before-broadcast) + recovery (leader lease, reattach, reconcile)
```

Hệ quả ràng buộc:

- **Không còn hai contract cho workspace.** Contract conversation (`/api/v2/conversations/*` + `/ws/conversations/{conversation_id}`) là **contract canonical duy nhất** cho UI workspace. Contract `/api/v2/sessions/*` chỉ còn là **execution primitive** (create/get/cancel session của runtime), không còn là API workspace để dựng UI 3 cột.
- **Frontend không tự chọn agent role.** Orchestrator quyết định spawn; UI chỉ hiển thị.
- **Stop theo `agent_instance_id`** — cancel agent B không ảnh hưởng A/C.
- **Run pin plan version cũ**; replan có chủ đích tạo version mới.
- **Tool chạy đúng một lần** qua idempotency key; **route lock** ghim canonical model + same-model failover.
- **Recovery boot** theo thứ tự cố định (Phase 6): leader lease → reattach live runtime → stop orphan → resume DAG → reconcile route locks → reconcile worktree → publish pending approvals.

### 3. Quyết định UI

- **`MultiAgentWorkspace` là UI workspace chính (canonical, target)** — conversation-based, normalized store `conversations[id] / agents[agent_instance_id] / sessions[agent_session_id] / events[agent_instance_id] / taskNodes[plan_version_id]`.
- **`AgentWorkspacePage` chỉ được giữ tạm sau feature flag** `VITE_WORKSPACE_UI=legacy`. Mọi mount trong `App.tsx` phải qua flag; **không được** mount cả hai cùng lúc.
- **Giá trị mặc định của flag giữ `legacy` cho tới khi backend conversation được wire** (Phase 2/3). Lý do: contract `/api/v2/conversations/*` chưa tồn tại (các hàm `fetchConversationAgents`/`fetchConversationTasks`/`updateTaskNode`... trong `apps/desktop/src/api/client.ts` đang trả `v2Unavailable`), nên chuyển default sang `multiagent` ngay sẽ thay UI đang chạy bằng UI trống không hoạt động. Phase 0 chỉ chốt kiến trúc; **cutover UI là Phase 7 (G8.x)** — lúc đó flip default sang `multiagent` và xóa `AgentWorkspacePage` + `agentSessionStore` hẳn (exit gate: `grep AgentWorkspace → 0`).
- **Không mock**: Browser panel chỉ hiển thị session/screenshot live của agent được chọn; không còn fallback "Awesome App".

### 4. Schema mapping V2 → multi-agent

Mapping chi tiết từng bảng V2 hiện tại sang schema multi-agent nằm ở
`docs/architecture/multi_agent_schema_mapping.md` (đính kèm ADR này, phần phụ lục A).

Nguyên tắc mapping:

- `chat_sessions` (V2) → `conversations` (Conversation aggregate) — migration dữ liệu giữ title/status/metadata.
- `v2_tasks` + `v2_workflow_runs`/`v2_workflow_steps` → `parent_tasks` + `task_plan_versions` + `task_nodes` + `task_edges` (TaskPlanVersion immutable).
- `task_runs`/`workflow_step_runs` → `task_node_runs` (TaskNodeRun; node state + retry + routing_snapshot persisted, không phụ thuộc in-memory).
- `execution_leases` → `tool_executions` (idempotency key unique) + `execution_leases` (concurrency_group/worktree lock).
- `agent_instances`/`agent_sessions` → canonical `agent_instances` + `agent_sessions` (unique `windagent_session_id`). **Lưu ý**: các bảng này hiện chỉ tồn tại trong legacy backend (`apps/backend`), **không** nằm trong canonical `windagent_storage` ORM — Phase 1 phải tạo mới trong canonical storage (xem `multi_agent_schema_mapping.md` §2.2).
- `route_locks_v3`/`route_attempts_v3`/`provider_routing_audit_v3` → giữ nguyên làm `route_locks` + `route_attempts` (RouteLock aggregate; bổ sung unique active per scope).
- `provider_credentials` → giữ nguyên + **AES-GCM/KMS encryption at rest** (G2.3), API chỉ trả metadata.

### 5. CI: writable tmp + full suite không timeout môi trường

- Toàn bộ test (architecture/unit/integration/regression) chạy trong CI (`.github/workflows/ci.yaml`) với **thư mục tạm ghi được** (export `TMPDIR`/`TEMP` tới workspace writable; test không ghi vào source tree).
- Mọi job test đặt `timeout` đủ lớn (≥1200s) cho full suite; không cắt giảm do môi trường.
- Test matrix gắn từng G1.1–G9.7 với test cụ thể nằm ở `docs/architecture/g1_g9_test_matrix.md` (phụ lục B).

## Consequences

- **Pros**: Một UI, một contract, một đường chạy — hết chi phí kép; orchestration cuối cùng có caller production; dữ liệu có baseline migration; acceptance G có test cụ thể trong matrix.
- **Cons**: `AgentWorkspacePage`/session-based UI bị deprecate (tạm giữ sau flag); phải viết lại một phần API client conversation; migration V2→multi-agent cần backup + rehearsal.
- **Risks**: Rủi ro phá vỡ UI đang dùng được giảm bằng feature flag (không xóa code trong Phase 0, chỉ chuyển default qua flag). Dữ liệu conversation cũ cần migration thủ công kiểm chứng (G1.1).

## References

- ADR 0001 (model pinning), 0002 (task DAG), 0003 (WS durable events), 0004 (worktree), 0005 (browser subprocess)
- `audit_report/AUDIT_agent_workspace_orchestration.md` (gap evidence)
- `ban_ke_hoach_v2.md` (roadmap Phase 0–9)
- `docs/architecture/multi_agent_schema_mapping.md` (phụ lục A)
- `docs/architecture/g1_g9_test_matrix.md` (phụ lục B)
