# MASTER PLAN

# Tái thiết WindAgent theo Architecture V2

## 1. Mục tiêu tổng thể

Tái cấu trúc WindAgent từ backend monolith hiện tại thành một **modular monolith có ranh giới package rõ ràng**, hỗ trợ:

* Nhiều giao diện: API, CLI, Web, Worker và Desktop.
* Nhiều model provider.
* Model routing theo năng lực, chi phí, quota và độ ổn định.
* Workflow dài hạn có state machine, retry, recovery và resume.
* Tool execution an toàn.
* Git worktree isolation cho coding agents.
* Context retrieval và memory nhiều lớp.
* Verification, quality gate và evaluation.
* Plugin, skill và MCP.
* Observability, audit và cost tracking.
* Khả năng tách process hoặc microservice về sau mà không phải viết lại domain core.

Không thực hiện big-bang rewrite. Kiến trúc mới phải chạy song song với backend hiện tại trong giai đoạn chuyển đổi.

---

# 2. Kiến trúc mục tiêu

```text
wind-agent/
├── apps/
│   ├── api/
│   ├── cli/
│   ├── web/
│   ├── worker/
│   ├── desktop/
│   └── backend/                 # legacy trong thời gian migration
│
├── core/
│   ├── domain/
│   ├── contracts/
│   ├── events/
│   ├── errors/
│   ├── config/
│   └── security/
│
├── orchestration/
│   ├── task_manager/
│   ├── workflow_engine/
│   ├── state_machine/
│   ├── scheduler/
│   ├── dispatcher/
│   ├── retry/
│   └── recovery/
│
├── intelligence/
│   ├── task_classifier/
│   ├── planner/
│   ├── context_builder/
│   ├── model_router/
│   ├── summarizer/
│   ├── reviewer/
│   └── reporter/
│
├── providers/
│   ├── base/
│   ├── openai/
│   ├── anthropic/
│   ├── google/
│   ├── nvidia/
│   ├── openrouter/
│   ├── mistral/
│   ├── ollama/
│   └── local/
│
├── tools/
│   ├── registry/
│   ├── filesystem/
│   ├── shell/
│   ├── git/
│   ├── code_search/
│   ├── ast/
│   ├── lsp/
│   ├── testing/
│   ├── browser/
│   ├── database/
│   ├── github/
│   └── mcp/
│
├── workflows/
├── verification/
├── context/
├── memory/
├── execution/
├── storage/
├── observability/
├── evals/
├── plugins/
├── skills/
├── scripts/
├── tests/
├── configs/
└── docs/
```

---

# 3. Quy tắc bắt buộc cho toàn bộ chương trình tái thiết

## 3.1 Không big-bang rewrite

Không được:

* Xóa `apps/backend` trước khi có parity test.
* Di chuyển hàng loạt service trong một commit.
* Thay đổi đồng thời API, database và event protocol.
* Đưa framework bên ngoài vào domain core.
* Rewrite frontend và backend trong cùng một phase.
* Tự động chuyển sang phase tiếp theo.

## 3.2 Mỗi phase là một đơn vị độc lập

Mỗi phase phải có:

* Branch riêng.
* Starting SHA.
* Scope rõ ràng.
* Test gate.
* Báo cáo cuối.
* Commit logic.
* Push remote.
* Draft PR.
* Worktree sạch.

Tên branch:

```text
refactor/architecture-v2-phase-00-baseline
refactor/architecture-v2-phase-01-scaffold
refactor/architecture-v2-phase-02-core-contracts
...
```

## 3.3 Quy tắc dependency

```text
apps
  ↓
workflows / orchestration / intelligence
  ↓
core contracts
  ↑
providers / tools / storage / execution / memory / context
```

Bắt buộc:

* `core` không import `apps`.
* `core/domain` không import FastAPI, SQLAlchemy, MCP, LangGraph hoặc provider SDK.
* `orchestration` không import provider implementation cụ thể.
* `intelligence/model_router` không trực tiếp gọi HTTP API provider.
* `tools` không tự bypass permission.
* `storage` không chứa business rule.
* `apps` chịu trách nhiệm composition và dependency injection.
* `plugins` không được import ngược vào domain core.

## 3.4 Fail-closed

Nếu gặp:

* Test regression.
* Migration không an toàn.
* API contract thay đổi ngoài dự kiến.
* Event incompatibility.
* Secret leak.
* Dependency cycle.
* Không thể chứng minh parity.

Antigravity phải dừng phase với verdict `blocked` hoặc `failed`, không tự giảm acceptance gate.

---

# 4. Luồng làm việc chuẩn cho mỗi phase

Antigravity phải thực hiện theo thứ tự:

```text
1. Kiểm tra repository và branch
2. Ghi baseline
3. Đọc tài liệu liên quan
4. Lập inventory phạm vi
5. Triển khai thay đổi nhỏ theo commit logic
6. Chạy focused tests
7. Chạy regression tests
8. Chạy architecture/integrity checks
9. Cập nhật tài liệu
10. Commit
11. Push
12. Tạo draft PR
13. Xuất báo cáo
14. Dừng
```

Không chạy nhiều full test suite đồng thời trên cùng database SQLite.

---

# PHASE 0 — BASELINE, INVENTORY VÀ FREEZE CONTRACT

## Mục tiêu

Chụp chính xác trạng thái hiện tại của WindAgent trước khi tái cấu trúc.

Không thay đổi behavior.

## Phạm vi

Chỉ:

* Inventory.
* Script audit.
* Tài liệu.
* Artifact baseline.
* Contract snapshot.

Không sửa business logic.

## Công việc

### 0.1 Repository baseline

Ghi nhận:

* Repository.
* Current branch.
* Starting SHA.
* Remote SHA.
* Worktree status.
* Python version.
* Node version.
* npm version.
* Rust và Tauri version nếu có.
* Database migration head.
* Test command hiện tại.

### 0.2 API inventory

Liệt kê toàn bộ:

* REST route.
* HTTP method.
* Request schema.
* Response schema.
* Status code.
* Router source.
* Service dependency.
* Authentication/permission requirement.

Xuất:

```text
artifacts/architecture_v2/baseline/api_inventory.json
```

### 0.3 Event inventory

Liệt kê:

* Event name.
* Payload.
* Sequence semantics.
* Producer.
* Consumer.
* Persistence.
* Replay behavior.
* WebSocket compatibility.

Xuất:

```text
artifacts/architecture_v2/baseline/event_inventory.json
```

### 0.4 Database inventory

Liệt kê:

* Table.
* Column.
* Index.
* Foreign key.
* Migration revision.
* ORM source.
* Service sử dụng.

### 0.5 Service dependency graph

Phân tích import và construction trong backend:

```text
main
→ database
→ event bus
→ model service
→ router
→ workflow
→ Hermes
→ browser
→ worktree
→ recovery
```

Xuất Mermaid hoặc JSON graph.

### 0.6 Test baseline

Chạy tuần tự:

* Focused backend.
* Full backend.
* Frontend unit.
* Frontend type-check.
* Frontend production build.
* Migration check.
* `git diff --check`.

Không sửa test để làm xanh.

## Đầu ra

```text
docs/architecture/current-system.md
docs/architecture/legacy-dependency-map.md
artifacts/architecture_v2/baseline/baseline_receipt.json
artifacts/architecture_v2/baseline/api_inventory.json
artifacts/architecture_v2/baseline/event_inventory.json
artifacts/architecture_v2/baseline/database_inventory.json
artifacts/architecture_v2/baseline/dependency_graph.json
```

## Acceptance gate

* Không có source behavior change.
* Baseline có thể tái tạo.
* API, event và database inventory đầy đủ.
* Test result được ghi chính xác.
* Worktree sạch sau commit.

## Prompt cho Antigravity

```text
Thực hiện PHASE 0 của chương trình Architecture V2 cho repository WindFaculty/WindAgent.

Mục tiêu duy nhất là chụp baseline và inventory. Không sửa business logic, API behavior, database schema hoặc event protocol.

Hãy:
1. Xác nhận branch, starting SHA, remote SHA và worktree.
2. Inventory toàn bộ REST, WebSocket, event, ORM table, migration, service và dependency.
3. Chạy tuần tự các test hiện có; không chạy nhiều full suite đồng thời.
4. Tạo baseline receipt và các artifact theo master plan.
5. Viết docs/architecture/current-system.md và legacy-dependency-map.md.
6. Commit, push và tạo draft PR.
7. Báo cáo đúng template cuối chương trình.
8. Dừng hoàn toàn sau PHASE 0. Không thực hiện PHASE 1.
```

---

# PHASE 1 — ARCHITECTURE SCAFFOLD VÀ UV WORKSPACE

## Mục tiêu

Dựng bộ khung Architecture V2 mà chưa di chuyển production logic.

## Công việc

### 1.1 Tạo root workspace

Tạo root `pyproject.toml` với `uv workspace`.

Các member ban đầu:

```text
apps/api
apps/cli
apps/worker
core
orchestration
intelligence
providers
tools
workflows
verification
context
memory
execution
storage
observability
evals
```

Không xóa `apps/backend/pyproject.toml`.

### 1.2 Namespace package

Dùng package rõ ràng:

```text
windagent_core
windagent_orchestration
windagent_intelligence
windagent_providers
windagent_tools
windagent_storage
windagent_execution
```

Không import kiểu:

```python
from core import ...
from tools import ...
```

### 1.3 Scaffold generator

Tạo:

```text
scripts/scaffold_architecture_v2.py
configs/architecture/scaffold_v2.yaml
```

Script phải hỗ trợ:

```text
--dry-run
--check
--create
```

Chạy lần hai phải tạo zero diff.

### 1.4 README cho bounded context

Mỗi top-level module phải có:

* Responsibility.
* Public API dự kiến.
* Allowed dependencies.
* Forbidden dependencies.
* Legacy migration source.
* Out-of-scope.
* Acceptance criteria.

### 1.5 API skeleton

Tạo API V2 độc lập:

```text
GET /health/live
GET /health/ready
GET /internal/architecture
```

Không mount `/api/v1` legacy.

### 1.6 Worker skeleton

Có:

* Startup.
* Shutdown.
* Cancellation.
* Readiness.
* Structured logging.
* No-op consumer.

### 1.7 CLI skeleton

Có:

```text
windagent doctor
windagent architecture check
```

### 1.8 Architecture import checker

Cấm dependency sai chiều.

## Acceptance gate

* Root `uv sync --all-packages` pass.
* Mỗi package import được.
* API skeleton smoke pass.
* Worker startup/shutdown pass.
* CLI doctor pass.
* Scaffold idempotent.
* Legacy regression không đổi.
* Không có migration mới.
* Không đổi API/event contract.

## Prompt cho Antigravity

```text
Thực hiện PHASE 1 Architecture V2: scaffold và uv workspace.

Dựa trên artifact PHASE 0. Chỉ dựng cấu trúc mới chạy song song; không di chuyển production services khỏi apps/backend.

Hãy:
1. Tạo branch refactor/architecture-v2-phase-01-scaffold từ main mới nhất đã chứa PHASE 0.
2. Tạo uv workspace và các namespace packages.
3. Tạo scaffold generator idempotent.
4. Tạo README boundary cho từng module.
5. Tạo API, Worker và CLI skeleton tối thiểu.
6. Thêm import-boundary checker và CI gate.
7. Chứng minh không thay đổi API, event và database legacy.
8. Chạy toàn bộ acceptance gate.
9. Commit theo nhóm logic, push, tạo draft PR và dừng.
Không di chuyển service legacy và không thực hiện PHASE 2.
```

---

# PHASE 2 — CORE DOMAIN, CONTRACTS, ERRORS, CONFIG VÀ SECURITY TYPES

## Mục tiêu

Xây domain vocabulary và contracts thuần Python.

## Domain objects tối thiểu

```text
Task
TaskRequest
TaskRun
Session
WorkflowDefinition
WorkflowRun
WorkflowStep
ToolInvocation
ToolResult
ModelRequest
ModelResponse
ArtifactRef
PermissionRequest
VerificationResult
```

## Typed identifiers

```text
TaskId
RunId
SessionId
WorkflowId
StepId
ToolCallId
ModelCallId
EventId
ArtifactId
```

Không truyền UUID bằng string khắp domain.

## Contract ports

```text
Clock
IdGenerator
TaskRepository
SessionRepository
WorkflowRepository
EventStore
EventPublisher
ArtifactRepository
UnitOfWork
SecretStore
PermissionEvaluator
```

## Error hierarchy

```text
WindAgentError
DomainError
ValidationError
ConflictError
NotFoundError
PermissionDeniedError
RetryableError
NonRetryableError
ProviderError
ToolError
IntegrityError
```

Error phải có:

* Stable code.
* Human message.
* Retryability.
* Metadata an toàn.
* Không chứa secret.

## Configuration

Tạo typed settings:

```text
CoreSettings
DatabaseSettings
ProviderSettings
ExecutionSettings
SecuritySettings
ObservabilitySettings
```

Không đọc `os.environ` trực tiếp trong domain hoặc use case.

## Security types

```text
Principal
Permission
ResourceScope
RiskLevel
ApprovalRequirement
SecretRef
RedactedValue
```

## Adapter compatibility

Tạo mapper giữa:

* Legacy Pydantic schema.
* Domain objects mới.

Không thay endpoint.

## Acceptance gate

* `core` không có dependency FastAPI/SQLAlchemy.
* Domain test thuần, không cần database.
* Invalid state bị chặn tại construction.
* Error codes ổn định.
* Config secret không xuất hiện trong repr/log.
* Legacy compatibility mapper pass.

## Prompt cho Antigravity

```text
Thực hiện PHASE 2 Architecture V2: Core Domain và Contracts.

Chỉ xây các package thuần Python trong core. Không thay runtime production.

Yêu cầu:
1. Tạo typed identifiers và domain objects tối thiểu.
2. Tạo contracts dưới dạng Protocol/ABC phù hợp.
3. Tạo error hierarchy với stable error code và retry classification.
4. Tạo typed configuration và security primitives.
5. Tạo compatibility mappers với schema legacy.
6. Viết unit tests cho invariant, serialization và secret redaction.
7. Chứng minh core không import FastAPI, SQLAlchemy, MCP, LangGraph hay provider SDK.
8. Chạy regression legacy, commit, push, draft PR và dừng.
Không thực hiện storage implementation hoặc PHASE 3.
```

---

# PHASE 3 — EVENT MODEL V2 VÀ COMPATIBILITY PROTOCOL

## Mục tiêu

Chuẩn hóa event nội bộ nhưng giữ tương thích WebSocket hiện tại.

## Event envelope V2

```text
event_id
event_type
schema_version
occurred_at
session_id
aggregate_id
sequence
correlation_id
causation_id
trace_id
payload
metadata
```

## Event semantics

Phải hỗ trợ:

* Monotonic sequence theo session.
* Persist-before-broadcast.
* Idempotency.
* Replay after sequence.
* Deduplication.
* Versioning.
* Correlation.
* Causation.
* Redaction.
* Unknown event tolerance.

## Compatibility serializer

Vẫn sinh được:

```json
{
  "event": "step_started",
  "timestamp": "...",
  "seq": 123,
  "data": {}
}
```

## Event catalog

Tạo registry cho:

```text
task.*
session.*
planning.*
workflow.*
step.*
tool.*
model.*
permission.*
verification.*
recovery.*
worktree.*
provider.*
system.*
```

## Không full Event Sourcing

Phase này không thay current-state database bằng event reconstruction.

Chỉ xây:

```text
durable execution event
+ compatibility
+ versioning
+ replay contract
```

## Acceptance gate

* Legacy event fixtures serialize giống trước.
* Replay after sequence pass.
* Duplicate event không tạo duplicate state.
* Event schema version được validate.
* Secret redaction pass.
* Unknown future event không crash UI consumer.
* Không thay route WebSocket ngoài dự kiến.

## Prompt cho Antigravity

```text
Thực hiện PHASE 3 Architecture V2: Event Model và Compatibility Protocol.

Không triển khai full Event Sourcing.

Hãy:
1. Tạo EventEnvelope V2, event catalog và schema versioning.
2. Giữ tương thích byte/shape cần thiết với legacy WebSocket events.
3. Tạo serializer, deserializer, redaction và idempotency helpers.
4. Tạo replay contract theo after_seq.
5. Viết fixture parity cho toàn bộ event inventory PHASE 0.
6. Không sửa UI protocol nếu chưa có compatibility adapter.
7. Chạy event regression, backend regression, commit, push, draft PR và dừng.
Không thực hiện PHASE 4.
```

---

# PHASE 4 — STORAGE, REPOSITORIES, UNIT OF WORK VÀ OUTBOX

## Mục tiêu

Tách persistence khỏi domain và service.

## Công việc

### 4.1 Storage package

```text
storage/database
storage/repositories
storage/artifacts
storage/logs
storage/cache
storage/migrations
```

### 4.2 ORM tách khỏi domain

Domain objects không kế thừa ORM.

Tạo mapper:

```text
Domain ↔ ORM
Domain ↔ persistence DTO
```

### 4.3 Repository implementations

Triển khai:

```text
SqlTaskRepository
SqlSessionRepository
SqlWorkflowRepository
SqlEventStore
FileArtifactRepository
SqlProviderConfigurationRepository
```

### 4.4 Unit of Work

Bảo đảm atomic transaction cho:

```text
state update
+ append event
+ outbox record
```

### 4.5 Transactional outbox

Không publish event trực tiếp trước khi transaction commit.

Flow:

```text
BEGIN
update current state
append event
append outbox
COMMIT
outbox publisher gửi event
```

### 4.6 Migration safety

* Không destructive migration.
* Có upgrade/downgrade.
* Có migration test trên database copy.
* Có schema checksum.
* Không sửa migration cũ đã áp dụng.

## Acceptance gate

* Repository contract tests pass.
* Rollback transaction pass.
* Outbox retry không duplicate.
* Migration upgrade/downgrade pass.
* Legacy DB đọc được.
* Không mất dữ liệu fixture.
* Concurrent update có conflict handling.
* Event và state atomic.

## Prompt cho Antigravity

```text
Thực hiện PHASE 4 Architecture V2: Storage, Repository, Unit of Work và Transactional Outbox.

Yêu cầu:
1. Tách ORM khỏi domain.
2. Implement repository ports từ PHASE 2.
3. Implement Unit of Work và transactional outbox.
4. Duy trì tương thích database legacy.
5. Chỉ thêm migration additive, không destructive.
6. Viết repository contract tests, rollback tests, concurrency tests và migration tests.
7. Không chuyển toàn bộ service production sang repository mới trong một lần.
8. Thêm adapter song song và parity tests.
9. Commit, push, draft PR và dừng.
Không thực hiện PHASE 5.
```

---

# PHASE 5 — PROVIDER PLATFORM VÀ MODEL ROUTER

## Mục tiêu

Tách provider implementation khỏi routing policy.

## Provider contract

```text
list_models
health
generate
stream
estimate_cost
get_quota
cancel
capabilities
```

## Provider adapters

Từng adapter riêng:

```text
OpenAI-compatible
Anthropic
Google
NVIDIA
OpenRouter
Mistral
Ollama
Local
```

Không triển khai tất cả logic trong một gateway file.

## Capability model

```text
chat
reasoning
coding
tool_use
vision
embedding
structured_output
long_context
streaming
computer_use
```

## Router input

```text
task type
required capabilities
context size
privacy requirement
latency target
budget
quota
provider health
historical eval
failure history
fallback policy
```

## Router output

```text
selected provider
selected model
selection reasons
fallback chain
estimated cost
route lock
policy version
```

## Route lock

Một task/run phải có:

* Canonical model selection.
* Same-model retry.
* Compatible fallback.
* Explicit escalation.
* Route audit.

## Không dùng keyword router đơn giản

Không được chỉ dựa vào:

* Prompt length.
* Một vài từ khóa.
* Provider order cố định.

## Acceptance gate

* Adapter contract tests.
* Mock provider tests.
* Timeout tests.
* Rate-limit tests.
* Quota exhaustion.
* Fallback.
* Route lock.
* Streaming cancellation.
* Cost accounting.
* Secret redaction.
* Không gửi request thật trong unit tests.

## Prompt cho Antigravity

```text
Thực hiện PHASE 5 Architecture V2: Provider Platform và Model Router.

Hãy:
1. Tạo provider base contracts và capability model.
2. Tách từng provider thành adapter độc lập.
3. Tạo router policy dựa trên capability, health, quota, latency, cost và eval evidence.
4. Tạo route lock, fallback chain và escalation.
5. Giữ compatibility với provider/model registry legacy.
6. Viết contract tests bằng mock/fake transport.
7. Không hard-code model mặc định vào domain.
8. Không gọi API thật trong test.
9. Chạy regression, commit, push, draft PR và dừng.
Không thực hiện PHASE 6.
```

---

# PHASE 6 — TOOL PLATFORM, EXECUTION VÀ PERMISSION ENGINE

## Mục tiêu

Xây tool runtime thống nhất và an toàn.

## Tool contract

```text
ToolDefinition
ToolInvocation
ToolExecutionContext
ToolResult
ToolError
```

## Tool registry

Hỗ trợ:

* Registration.
* Version.
* Schema.
* Capability.
* Risk.
* Permission.
* Timeout.
* Resource requirements.
* Deterministic audit.

## Tool groups

```text
filesystem
shell
git
code_search
ast
lsp
testing
browser
database
github
mcp
```

## Execution

```text
sandbox
worktree
process_manager
resource_limits
permissions
environments
```

## Permission engine

Phân loại:

```text
read-only
workspace-write
external-network
secret-access
process-execution
destructive
privileged
```

Mọi tool call phải được policy engine đánh giá trước.

## Shell safety

Có:

* Working directory boundary.
* Command allow/deny policy.
* Timeout.
* Output limit.
* Process tree termination.
* Secret masking.
* No shell interpolation không kiểm soát.
* Audit log.

## Filesystem safety

* Path traversal protection.
* Symlink escape protection.
* Workspace root enforcement.
* Atomic write.
* Backup hoặc patch artifact.
* File size limit.

## Acceptance gate

* Tool schema validation.
* Path traversal tests.
* Symlink escape tests.
* Timeout and cancellation.
* Process cleanup.
* Permission approval/denial.
* Audit completeness.
* No secret in logs.
* Existing tools chạy qua compatibility adapter.

## Prompt cho Antigravity

```text
Thực hiện PHASE 6 Architecture V2: Tool Platform, Execution và Permission Engine.

Yêu cầu:
1. Tạo tool contracts và registry có version/schema/risk.
2. Tạo process manager, resource limits và workspace boundary.
3. Tạo permission policy bắt buộc trước mọi tool call.
4. Adapter các tool legacy vào registry mới, không rewrite đồng thời.
5. Thêm traversal, symlink, timeout, cancellation và secret-redaction tests.
6. Không cho agent tự bypass approval.
7. Không thêm unrestricted shell mode mặc định.
8. Chạy security regression, commit, push, draft PR và dừng.
Không thực hiện PHASE 7.
```

---

# PHASE 7 — PLUGINS, SKILLS VÀ MCP

## Mục tiêu

Xây extension platform nhưng không để plugin phá vỡ core.

## Plugin manifest

```text
id
name
version
entrypoint
capabilities
required_permissions
required_tools
config_schema
compatibility
signature/hash
```

## Skill manifest

```text
id
version
description
activation_rules
required_tools
required_permissions
token_budget
prompt_template
verification_policy
```

## MCP architecture

MCP là adapter của WindAgent tool system:

```text
MCP server
→ MCP client adapter
→ WindAgent ToolDefinition
→ Permission engine
→ Tool registry
```

Không để MCP tool gọi trực tiếp execution layer ngoài policy.

## MCP support

* `stdio`.
* Streamable HTTP.
* Tool listing.
* Tool calling.
* Resources.
* Prompts.
* Cancellation.
* Timeout.
* Server lifecycle.
* Permission scope.

Dùng SDK chính thức được pin version.

## Plugin security

* Disabled by default.
* Allowlist.
* Version pin.
* Hash verification.
* Static manifest validation.
* No arbitrary auto-install.
* No implicit secret access.
* No unrestricted subprocess.

## Acceptance gate

* Invalid manifest bị reject.
* Duplicate plugin/skill ID bị reject.
* MCP disconnect recovery.
* Malicious tool schema bị reject.
* Permission enforcement.
* Skill lazy loading.
* Token budget.
* Plugin failure không làm crash core.

## Prompt cho Antigravity

```text
Thực hiện PHASE 7 Architecture V2: Plugins, Skills và MCP.

Hãy:
1. Tạo plugin và skill manifests có version, permission và compatibility.
2. Tạo internal MCPClientPort và adapter bằng SDK MCP chính thức.
3. Map MCP tools vào WindAgent ToolDefinition.
4. Bắt buộc mọi MCP call đi qua permission engine.
5. Plugin/skill disabled by default và không auto-install.
6. Viết security, lifecycle, timeout và compatibility tests.
7. Không dùng mcp2py làm dependency lõi.
8. Commit, push, draft PR và dừng.
Không thực hiện PHASE 8.
```

---

# PHASE 8 — ORCHESTRATION ENGINE, STATE MACHINE, RETRY VÀ RECOVERY

## Mục tiêu

Xây runtime điều phối deterministic.

## Task state machine

```text
RECEIVED
CLASSIFYING
CONTEXT_BUILDING
PLANNING
READY
RUNNING
WAITING_PERMISSION
PAUSED
RETRY_WAIT
RECOVERING
VERIFYING
REVIEWING
COMPLETED
FAILED
CANCELLED
```

Mọi transition phải được validate.

## Components

```text
TaskManager
WorkflowEngine
StateMachine
Scheduler
Dispatcher
RetryPolicy
RecoveryManager
CancellationManager
```

## Durable facts, derived status

Lưu fact:

```text
current step
last sequence
runtime alive
pending permission
retry count
last error
verification state
```

UI status được derive, không lưu nhiều status trùng nhau.

## Retry policy

Dựa trên:

* Error classification.
* Attempt.
* Tool/provider.
* Idempotency.
* Backoff.
* Budget.
* Deadline.

Không retry lỗi non-retryable.

## Recovery

Khi restart:

* Tìm run in-flight.
* Kiểm tra runtime.
* Reconcile state.
* Resume hoặc fail rõ ràng.
* Không chạy lại tool destructive nếu chưa chứng minh idempotent.

## Scheduler

* Bounded concurrency.
* Priority.
* Resource limits.
* Per-project lock.
* Per-worktree ownership.
* Cancellation.
* Fairness.

## Acceptance gate

* State transition table tests.
* Invalid transition rejected.
* Pause/resume.
* Cancel.
* Crash recovery.
* Duplicate dispatch.
* Retry exhaustion.
* Idempotent resume.
* Concurrent task isolation.
* No destructive replay.

## Prompt cho Antigravity

```text
Thực hiện PHASE 8 Architecture V2: Orchestration Engine và State Machine.

Yêu cầu:
1. Tạo explicit state machine và transition table.
2. Tách TaskManager, Scheduler, Dispatcher, Retry và Recovery.
3. Dùng durable facts và derived status.
4. Bảo đảm idempotency, bounded concurrency và cancellation.
5. Adapter workflow runner/DAG scheduler legacy từng phần.
6. Viết crash/restart, duplicate dispatch, pause/resume và retry tests.
7. Không tự động chạy lại destructive tool.
8. Chạy regression, commit, push, draft PR và dừng.
Không thực hiện PHASE 9.
```

---

# PHASE 9 — CONTEXT, REPOSITORY INTELLIGENCE VÀ MEMORY

## Mục tiêu

Tạo context system có ngân sách và provenance rõ ràng.

## Repository intelligence

```text
repository_index
retrieval
dependency_graph
symbol_graph
code_search
AST index
LSP integration
change index
```

## Context builder

Context phải ghi:

* Source.
* File.
* Line.
* Retrieval reason.
* Token cost.
* Freshness.
* Confidence.
* Truncation.
* Access permission.

## Compaction

* Conversation compaction.
* Tool result compaction.
* Repository context compaction.
* Preserve decisions and errors.
* Không làm mất acceptance criteria.
* Có reversible reference tới artifact gốc.

## Memory layers

```text
session
project
user
episodic
vector_store
```

Không ghi mọi thứ vào vector store.

## Memory write policy

Chỉ ghi khi:

* Có giá trị tái sử dụng.
* Không chứa secret.
* Có provenance.
* Có scope.
* Có retention policy.
* Có conflict handling.

## Acceptance gate

* Retrieval precision fixture.
* Token budget enforcement.
* Stale context detection.
* Secret exclusion.
* Cross-project isolation.
* Compaction retention.
* Memory delete/update.
* No vector-only source of truth.

## Prompt cho Antigravity

```text
Thực hiện PHASE 9 Architecture V2: Context và Memory.

Hãy:
1. Tạo repository index, symbol/dependency graph và retrieval ports.
2. Tạo context builder có provenance, freshness và token budget.
3. Tạo compaction giữ lại decision, blocker và acceptance criteria.
4. Tạo session/project/user/episodic memory với scope rõ ràng.
5. Không đưa mọi dữ liệu vào vector store.
6. Viết retrieval, isolation, stale-data, secret và token-budget tests.
7. Không thay orchestration behavior ngoài integration adapter.
8. Commit, push, draft PR và dừng.
Không thực hiện PHASE 10.
```

---

# PHASE 10 — WORKFLOW PACKS

## Mục tiêu

Chuẩn hóa từng loại nhiệm vụ thành workflow package.

## Workflow package contract

Mỗi workflow có:

```text
metadata
input schema
classification rule
planning policy
allowed tools
model requirements
permission policy
retry policy
verification policy
acceptance criteria
report format
```

## Thứ tự triển khai

### 10.1 Bugfix

Flow:

```text
reproduce
diagnose
patch
focused test
regression
review
report
```

### 10.2 CI fix

```text
inspect checks
read logs
identify root cause
patch
rerun focused CI
report
```

### 10.3 Code review

```text
diff inventory
risk classification
correctness
security
tests
review report
```

### 10.4 Feature

```text
requirements
design
implementation
tests
acceptance
report
```

### 10.5 Refactor

```text
baseline behavior
dependency map
incremental change
parity test
regression
```

### 10.6 Research

```text
question decomposition
source collection
source quality
synthesis
citation
artifact
```

### 10.7 Scientific evaluation

```text
protocol freeze
data integrity
leakage checks
execution
metrics
reproduction
verdict
```

### 10.8 Release

```text
version
changelog
build
security scan
artifact checksum
smoke
rollback plan
```

## Acceptance gate

* Workflow schema validation.
* Tool policy enforcement.
* Deterministic state progression.
* Acceptance criteria machine-readable.
* Failure path tests.
* Golden workflow replay.
* Không workflow nào tự merge hoặc release nếu chưa được cấp quyền.

## Prompt cho Antigravity

```text
Thực hiện PHASE 10 Architecture V2: Workflow Packs.

Hãy:
1. Tạo workflow package contract.
2. Implement lần lượt bugfix, ci_fix, code_review, feature, refactor, research, scientific_eval và release.
3. Mỗi workflow phải khai báo tool, model, permission, retry, verification và acceptance.
4. Dùng orchestrator PHASE 8; không tạo runtime riêng trong từng workflow.
5. Tạo golden fixtures và failure-path tests.
6. Không auto-merge hoặc auto-release mặc định.
7. Commit, push, draft PR và dừng.
Không thực hiện PHASE 11.
```

---

# PHASE 11 — VERIFICATION, EVALS VÀ OBSERVABILITY

## Mục tiêu

Đo được hệ thống có thực sự hoạt động hay chỉ chạy không lỗi.

## Verification

```text
test_runner
policy_engine
integrity
quality_gates
regression
security
acceptance
```

## Verification result

```text
gate
status
evidence
command
exit code
artifact
duration
blocking
```

## Evals

```text
datasets
graders
benchmarks
replay
reports
```

Benchmark tối thiểu:

* Bugfix.
* Feature.
* CI repair.
* Code review.
* Research.
* Tool selection.
* Model routing.
* Recovery.
* Permission safety.
* Cost.

## Metrics

```text
task success rate
accepted task rate
first-pass success
recovery success
tool failure
provider failure
tokens
cost
latency
human intervention
retry count
context size
verification failure
```

## Tracing

Trace chain:

```text
task
→ plan
→ workflow
→ step
→ model call
→ tool call
→ verification
```

## Audit

Audit event phải chứa:

* Actor.
* Action.
* Resource.
* Decision.
* Policy.
* Correlation.
* Result.
* Timestamp.

Không chứa secret hoặc raw sensitive data.

## Acceptance gate

* Trace completeness.
* Cost reconciliation.
* Audit ordering.
* Eval deterministic fixture.
* Replay.
* Security gate.
* Report validation.
* Dashboard không phụ thuộc trực tiếp vào provider implementation.

## Prompt cho Antigravity

```text
Thực hiện PHASE 11 Architecture V2: Verification, Evals và Observability.

Hãy:
1. Tạo verification contracts và quality gates.
2. Tạo benchmark/eval datasets và graders tối thiểu.
3. Tạo trace task→workflow→model/tool→verification.
4. Tạo cost, latency, retry và intervention metrics.
5. Tạo audit log có correlation nhưng không chứa secret.
6. Tạo replay và report validator.
7. Không coi test pass là bằng chứng duy nhất của agent quality.
8. Commit, push, draft PR và dừng.
Không thực hiện PHASE 12.
```

---

# PHASE 12 — API V2, WORKER VÀ CLI PRODUCTION INTEGRATION

## Mục tiêu

Đưa Architecture V2 vào các process thật nhưng vẫn giữ legacy fallback.

## API V2

Tạo:

```text
/api/v2/tasks
/api/v2/runs
/api/v2/workflows
/api/v2/events
/api/v2/providers
/api/v2/tools
/api/v2/permissions
/api/v2/artifacts
/api/v2/evals
```

## Worker

Worker chịu trách nhiệm:

* Claim task.
* Heartbeat.
* Execute workflow.
* Renew lease.
* Handle cancellation.
* Emit events.
* Recover abandoned task.

## CLI

Các lệnh:

```text
windagent doctor
windagent run
windagent status
windagent task list
windagent task inspect
windagent replay
windagent providers
windagent tools
windagent eval
windagent architecture check
```

## Compatibility

* `/api/v1` vẫn hoạt động.
* V1 có thể gọi V2 application service qua adapter.
* Không duplicate business rule trong V1 và V2.
* Có route parity matrix.

## Acceptance gate

* API contract tests.
* Worker lease tests.
* Multi-worker claim safety.
* Cancellation.
* Event stream.
* CLI E2E.
* V1/V2 compatibility.
* Recovery after worker crash.
* No duplicate execution.

## Prompt cho Antigravity

```text
Thực hiện PHASE 12 Architecture V2: API V2, Worker và CLI integration.

Yêu cầu:
1. Tạo API V2 trên application services mới.
2. Tạo production worker có lease, heartbeat, cancellation và recovery.
3. Hoàn thiện CLI.
4. Giữ /api/v1 hoạt động qua compatibility adapter.
5. Không duplicate business logic giữa V1 và V2.
6. Tạo parity matrix và E2E tests.
7. Chạy legacy regression và V2 E2E.
8. Commit, push, draft PR và dừng.
Không thực hiện PHASE 13.
```

---

# PHASE 13 — TÁCH WEB APP VÀ DESKTOP SHELL

## Mục tiêu

Tách React application khỏi Tauri shell mà không tạo hai frontend độc lập.

## Cấu trúc

```text
apps/web
├── src
├── tests
└── package.json

apps/desktop
├── src-tauri
├── desktop bootstrap
└── packaging
```

Desktop dùng build artifact của `apps/web`.

## Frontend architecture

```text
features/
entities/
shared/
app/
```

Các client:

```text
api client
event stream client
artifact client
permission client
provider client
```

## State recovery

UI phải hỗ trợ:

* Refresh recovery.
* Tab switch.
* Event replay.
* Reconnect.
* Deduplication.
* Pending permission restoration.
* Task/run history.
* Worker disconnected state.

## Desktop shell

Chịu trách nhiệm:

* Spawn API sidecar.
* Spawn worker.
* Health monitoring.
* Shutdown.
* Log location.
* Update.
* Native permission.
* File dialog.
* Packaging.

Không chứa business logic orchestration.

## Acceptance gate

* Web chạy độc lập.
* Desktop dùng cùng web build.
* No duplicated UI.
* Refresh recovery.
* Offline/error state.
* Event reconnect.
* Production web build.
* Tauri build khi môi trường hỗ trợ.
* Sidecar lifecycle test.

## Prompt cho Antigravity

```text
Thực hiện PHASE 13 Architecture V2: tách Web App và Desktop Shell.

Hãy:
1. Di chuyển React app vào apps/web theo từng bước có compatibility.
2. Giữ Tauri shell trong apps/desktop.
3. Desktop phải dùng cùng web build, không fork UI.
4. Tách API/event clients khỏi component.
5. Implement refresh recovery, reconnect và dedupe.
6. Tạo sidecar lifecycle và packaging tests.
7. Không sửa backend domain trong phase này trừ compatibility cần thiết.
8. Commit, push, draft PR và dừng.
Không thực hiện PHASE 14.
```

---

# PHASE 14 — MIGRATION LEGACY, CUTOVER VÀ DECOMMISSION

## Mục tiêu

Chuyển production traffic sang V2 và loại bỏ legacy có kiểm soát.

## Điều kiện trước khi bắt đầu

Bắt buộc:

* API parity.
* Event parity.
* Database parity.
* Workflow parity.
* Provider parity.
* Tool parity.
* Recovery parity.
* Desktop E2E.
* Evaluation baseline.
* Rollback plan.

Nếu thiếu bất kỳ gate nào, phase bị block.

## Migration strategy

### 14.1 Strangler cutover

Chuyển từng capability:

```text
health
sessions
tasks
events
providers
tools
workflows
browser
Hermes
worktrees
```

### 14.2 Feature flags

```text
WINDAGENT_ARCH_V2
WINDAGENT_V2_TASKS
WINDAGENT_V2_PROVIDERS
WINDAGENT_V2_TOOLS
WINDAGENT_V2_WORKFLOWS
```

### 14.3 Shadow execution

Với operation read-only:

* Chạy V1 và V2.
* So sánh kết quả.
* Không trả V2 nếu chưa đạt parity.

Không shadow destructive tool.

### 14.4 Legacy deletion

Chỉ xóa file khi:

* Không còn import.
* Không còn route.
* Không còn test dependency.
* Không còn database ownership.
* Có replacement mapping.
* Có rollback tag trước deletion.

## Acceptance gate

* Full repository tests.
* Clean clone.
* Fresh database.
* Upgraded database.
* Desktop E2E.
* Worker crash recovery.
* Provider fallback.
* Tool security.
* API compatibility.
* Rollback rehearsal.
* No legacy import.

## Prompt cho Antigravity

```text
Thực hiện PHASE 14 Architecture V2: Legacy Migration, Cutover và Decommission.

Trước tiên kiểm tra toàn bộ prerequisite gate. Nếu thiếu bất kỳ parity hoặc rollback gate nào, dừng với verdict blocked.

Nếu đủ điều kiện:
1. Chuyển từng capability bằng feature flag.
2. Dùng shadow comparison cho read-only operation.
3. Không shadow destructive tool.
4. Xóa legacy theo dependency order, không xóa hàng loạt.
5. Tạo rollback tag và rollback procedure.
6. Chạy clean-clone, fresh-db, upgraded-db, desktop E2E và full regression.
7. Chứng minh zero legacy import.
8. Commit, push, draft PR và dừng.
Không tự merge vào main.
```

---

# 5. Template báo cáo bắt buộc sau mỗi phase

```text
FINAL VERDICT:
PHASE:
REPOSITORY:
STARTING BRANCH:
STARTING SHA:
FINAL BRANCH:
FINAL SHA:
REMOTE SHA == LOCAL:
WORKTREE CLEAN:

OBJECTIVE:
SCOPE COMPLETED:
OUT OF SCOPE:
FILES CREATED:
FILES MODIFIED:
FILES MOVED:
FILES DELETED:

ARCHITECTURE CHANGES:
DEPENDENCY CHANGES:
API CONTRACT CHANGES:
EVENT CONTRACT CHANGES:
DATABASE CHANGES:
MIGRATION STATUS:
SECURITY IMPACT:
COMPATIBILITY IMPACT:

FOCUSED TESTS:
REGRESSION TESTS:
ARCHITECTURE TESTS:
INTEGRATION TESTS:
E2E TESTS:
BUILD RESULTS:
GIT DIFF CHECK:

ACCEPTANCE GATES:
- gate:
  status:
  evidence:

KNOWN LIMITATIONS:
BLOCKERS:
RISKS:
ROLLBACK PROCEDURE:
NEXT RECOMMENDED PHASE:

COMMITS:
DRAFT PR:
```

---

# 6. Verdict hợp lệ

Antigravity chỉ được dùng các verdict sau:

```text
accepted
accepted_with_non_blocking_warnings
blocked_missing_dependency
blocked_environment
blocked_legacy_regression
blocked_contract_incompatibility
blocked_migration_risk
failed_acceptance_gate
invalid_run
```

Không sử dụng từ chung chung như:

```text
mostly done
looks good
probably works
production ready
```

nếu chưa có evidence.

---

# 7. Thứ tự merge

```text
PHASE 0
  ↓
PHASE 1
  ↓
PHASE 2
  ↓
PHASE 3
  ↓
PHASE 4
  ↓
PHASE 5 và PHASE 6
  ↓
PHASE 7
  ↓
PHASE 8
  ↓
PHASE 9
  ↓
PHASE 10
  ↓
PHASE 11
  ↓
PHASE 12
  ↓
PHASE 13
  ↓
PHASE 14
```

Phase 5 và 6 có thể phát triển trên các branch riêng sau Phase 4, nhưng không được merge nếu contract chung chưa ổn định.

---

# 8. Các quyết định kiến trúc không được tự ý thay đổi

Antigravity không được tự ý:

* Chuyển sang microservices.
* Áp dụng full Event Sourcing.
* Áp dụng full CQRS cho mọi operation.
* Thay SQLite bằng PostgreSQL trong scaffold phase.
* Đưa LangGraph thành domain kernel.
* Dùng CrewAI hoặc framework khác làm orchestration core.
* Cho MCP bypass tool registry.
* Cho plugin tự cài package.
* Cho LLM tự merge hoặc release.
* Xóa V1 trước parity.
* Hạ test gate để hoàn thành phase.
* Rewrite cả frontend và backend cùng lúc.

Mọi thay đổi các quyết định trên phải có ADR riêng và được người dùng phê duyệt.

---

# 9. Definition of Done toàn chương trình

Architecture V2 chỉ được coi là hoàn thành khi:

* Domain core không phụ thuộc framework.
* Package boundaries được CI cưỡng chế.
* API, CLI, Worker, Web và Desktop dùng chung application core.
* Provider adapter độc lập.
* Model router có evidence và cost tracking.
* Tool call luôn qua permission engine.
* Workflow có state machine, retry và recovery.
* Event có persistence, replay và versioning.
* Context có provenance và token budget.
* Memory có scope và retention.
* Verification gate có artifact.
* Eval đo success, cost và reliability.
* Observability trace xuyên suốt task.
* Desktop recovery sau refresh/restart.
* Legacy backend được loại bỏ hoặc chỉ còn compatibility shim có lịch xóa.
* Clean clone E2E pass.
* Rollback procedure được kiểm chứng.
* Không có secret trong repository, log hoặc artifact.
