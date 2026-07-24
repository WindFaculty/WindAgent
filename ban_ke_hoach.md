# IMPLEMENTATION PLAN — WINDAGENT CORE CANONICALIZATION AND FULL ADOPTION

## 1. Thông tin thực hiện

**Repository:** `WindFaculty/WindAgent`
**Starting commit:** `12ddf5f8d2e2bbb4325c8bf7e8ec1d1537ffa528`
**Nhánh đề xuất:** `refactor/core-canonical-full-adoption`
**Mục tiêu:** Hoàn thiện và đưa `windagent_core` thành shared kernel canonical thực sự cho toàn bộ WindAgent.

Cấu trúc đích:

```text
core/
└── windagent_core/
    ├── domain/
    ├── contracts/
    ├── events/
    ├── errors/
    ├── config/
    └── security/
```

## 2. Các quyết định kiến trúc đã khóa

1. Tiếp tục chính xác từ commit `12ddf5f8d2e2bbb4325c8bf7e8ec1d1537ffa528`.
2. Core là **shared kernel**, chỉ sở hữu các khái niệm đi qua ranh giới package.
3. Canonical model trong core sử dụng **Pydantic v2**.
4. ID sử dụng chiến lược hybrid:

   * Domain entity ID: UUID typed ID.
   * Provider, endpoint, runtime và external ID: opaque typed ID.
5. Core sở hữu:

   * Lifecycle state.
   * Legal transition matrix.
   * Domain invariant.
6. Event canonical sử dụng dotted taxonomy:

   * `task.created`
   * `workflow.started`
   * `step.completed`
   * `provider.request.failed`
7. Legacy event name chỉ được chuyển đổi tại API/WebSocket edge.
8. `core/config` chỉ chứa immutable typed schema và validation.
9. `core/security` chứa policy types, decision model và ports; không chứa Fernet, environment loader hoặc OS keychain implementation.
10. Toàn bộ orchestration, providers, storage, tools, API, worker và intelligence phải chuyển sang canonical core model.
11. Kết thúc chương trình không được còn duplicate canonical model.

---

# 3. Hiện trạng cần sửa

Core hiện được khai báo là package không có dependency, nhưng lựa chọn Pydantic v2 yêu cầu cập nhật quy tắc package để cho phép duy nhất dependency modeling đã phê duyệt. Hiện `core/pyproject.toml` đang có `dependencies = []`.

Core hiện đã chứa model, event, error, config và security sơ bộ, nhưng public API chưa export các protocol trong `contracts/protocols.py`.

Các duplicate lớn hiện tồn tại:

* Core và orchestration có hai `WorkflowDefinition` không tương thích. Core dùng ordered steps, trong khi orchestration dùng graph nodes và edges.
* Core và providers có hai hệ request/response model riêng.
* Core, orchestration và backend có các lifecycle enum riêng.
* Core, orchestration và backend có ba event envelope khác nhau.
* Provider subsystem có error hierarchy độc lập với `WindAgentError`.
* API V2 vẫn sử dụng mock/in-memory state và hard-coded timestamp.
* Security policy, secret encryption và permission evaluation vẫn phân tán giữa core và backend.

---

# 4. Kiến trúc đích

## 4.1 Cấu trúc package

```text
core/windagent_core/
├── __init__.py
│
├── domain/
│   ├── __init__.py
│   ├── ids.py
│   ├── lifecycle.py
│   ├── session.py
│   ├── task.py
│   ├── workflow.py
│   ├── execution.py
│   ├── model.py
│   ├── artifact.py
│   ├── permission.py
│   └── invariants.py
│
├── contracts/
│   ├── __init__.py
│   ├── clock.py
│   ├── repositories.py
│   ├── unit_of_work.py
│   ├── eventing.py
│   ├── execution.py
│   ├── providers.py
│   ├── security.py
│   └── observability.py
│
├── events/
│   ├── __init__.py
│   ├── names.py
│   ├── envelope.py
│   ├── registry.py
│   ├── payloads/
│   │   ├── task.py
│   │   ├── workflow.py
│   │   ├── execution.py
│   │   ├── provider.py
│   │   ├── permission.py
│   │   └── system.py
│   └── serialization.py
│
├── errors/
│   ├── __init__.py
│   ├── codes.py
│   ├── base.py
│   ├── domain.py
│   ├── concurrency.py
│   ├── execution.py
│   ├── provider.py
│   ├── security.py
│   └── serialization.py
│
├── config/
│   ├── __init__.py
│   ├── application.py
│   ├── database.py
│   ├── execution.py
│   ├── providers.py
│   ├── security.py
│   └── observability.py
│
└── security/
    ├── __init__.py
    ├── principal.py
    ├── permissions.py
    ├── decisions.py
    ├── scopes.py
    ├── secrets.py
    └── audit.py
```

## 4.2 Quy tắc dependency

Core được phép phụ thuộc:

```text
pydantic>=2.7
typing-extensions
```

Core bị cấm import:

```text
fastapi
sqlalchemy
aiosqlite
cryptography
httpx
apps.*
windagent_storage
windagent_orchestration
windagent_providers
windagent_tools
windagent_intelligence
```

`core/config` không được:

* Gọi `os.getenv`.
* Đọc file.
* Truy cập database.
* Mutate feature flag runtime.
* Thực thi shadow comparison.
* Khởi tạo secret implementation.

---

# 5. Canonical model specification

## 5.1 Typed IDs

Tách base ID hiện tại thành hai hệ riêng.

```python
class UUIDEntityId(RootModel[UUID]):
    ...

class OpaqueId(RootModel[str]):
    ...
```

### UUID domain IDs

```text
TaskId
TaskRunId
SessionId
WorkflowId
WorkflowRunId
StepId
StepRunId
EventId
ArtifactId
PermissionRequestId
ToolCallId
ModelCallId
```

### Opaque external/runtime IDs

```text
ProviderId
EndpointId
CanonicalModelId
ProviderModelId
RuntimeRunId
RuntimeSessionId
WorkerId
RouteLockId
RouteAttemptId
ExternalRequestId
```

Không giữ `to_uuid()` trên base class chung. Base ID hiện tại chấp nhận mọi string nhưng lại giả định có thể chuyển sang UUID, đây là invariant không an toàn.

### Quy tắc mapper

* Không tự sinh ID khi dữ liệu persisted bị thiếu ID.
* Không đổi ID lỗi thành ID mới.
* Không dùng workflow ID thay run ID.
* Dữ liệu không hợp lệ phải trả `IdentityValidationError`.
* ID chỉ được generate trong create command hoặc aggregate factory.

---

## 5.2 Lifecycle canonical

### TaskState

Sử dụng lifecycle 15 trạng thái hiện có của orchestration làm nền:

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

Danh sách này hiện đang nằm trong orchestration.

Chuyển vào:

```text
core/domain/lifecycle.py
```

### WorkflowState

```text
DRAFT
READY
RUNNING
PAUSED
COMPLETED
FAILED
CANCELLED
```

### StepState

```text
BLOCKED
READY
CLAIMED
DISPATCHED
RUNNING
WAITING_PERMISSION
RETRY_WAIT
COMPLETED
FAILED
SKIPPED
CANCELLED
```

### SessionState

```text
IDLE
ACTIVE
PAUSED
COMPLETED
FAILED
CANCELLED
ARCHIVED
```

### Transition ownership

Core phải cung cấp:

```python
TaskLifecycle.transition(current, target)
WorkflowLifecycle.transition(current, target)
StepLifecycle.transition(current, target)
SessionLifecycle.transition(current, target)
```

Mỗi transition trả canonical transition result hoặc raise:

```text
InvalidStateTransitionError
TerminalStateMutationError
ConcurrentStateConflictError
```

Orchestration không được tự định nghĩa transition matrix riêng sau cutover.

---

## 5.3 Workflow canonical

Canonical workflow cần hỗ trợ graph, không sử dụng ordered list đơn giản làm representation chính.

```python
class WorkflowDefinition(BaseModel):
    id: WorkflowId
    name: str
    version: int
    nodes: dict[StepId, WorkflowNode]
    edges: list[WorkflowEdge]
```

```python
class WorkflowNode(BaseModel):
    id: StepId
    name: str
    tool_name: str
    parameters: dict[str, JsonValue]
    priority: int
    timeout_seconds: float | None
    max_attempts: int
```

```python
class WorkflowEdge(BaseModel):
    source_step_id: StepId
    target_step_id: StepId
    condition: str | None
    edge_type: EdgeType
```

`order` chỉ là derived projection cho UI và legacy compatibility, không phải canonical execution invariant.

---

## 5.4 Provider shared contracts

Chỉ đưa vào core các model đi qua ranh giới providers ↔ intelligence ↔ orchestration:

```text
ModelRequest
ModelResponse
ModelStreamEvent
ModelUsage
ModelCapability
CanonicalModelRef
ProviderEndpointRef
ProviderFailureInfo
```

Giữ ngoài core:

```text
HTTP transport internals
Vendor response shapes
Protocol detection evidence
Cache backend records
Quota polling implementation
Endpoint health implementation
Provider-specific extension payloads
```

`ProviderRequest` và `ProviderResponse` hiện nằm trong providers phải được chuyển sang hoặc map trực tiếp vào canonical core model.

---

# 6. Canonical contracts

## Shared contracts bắt buộc

```text
Clock
IdGenerator
TaskRepository
TaskRunRepository
SessionRepository
WorkflowRepository
WorkflowRunRepository
EventStore
OutboxWriter
UnitOfWork
ExecutionRuntimePort
ModelGatewayPort
PermissionEvaluator
SecretStore
ArtifactRepository
AuditSink
```

## UnitOfWork canonical

```python
class UnitOfWork(Protocol):
    tasks: TaskRepository
    task_runs: TaskRunRepository
    workflows: WorkflowRepository
    workflow_runs: WorkflowRunRepository
    events: EventStore
    outbox: OutboxWriter

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
```

Không tiếp tục sử dụng UoW không expose repository như contract hiện tại.

## PermissionEvaluator canonical

Không trả `bool`.

```python
class PermissionEvaluator(Protocol):
    async def evaluate(
        self,
        request: PermissionEvaluationRequest,
    ) -> PermissionDecision:
        ...
```

`PermissionDecision` gồm:

```text
outcome: ALLOW | REQUIRE_APPROVAL | DENY
risk_level
reason_code
human_reason
policy_version
matched_rule
audit_metadata
```

## SecretStore canonical

Không trả plaintext `str` qua public API.

```python
class SecretStore(Protocol):
    async def resolve(self, ref: SecretRef) -> SecretValue: ...
    async def store(self, name: SecretName, value: SecretValue) -> SecretRef: ...
    async def delete(self, ref: SecretRef) -> None: ...
```

---

# 7. Canonical event model

## 7.1 Event naming

Dotted names là canonical duy nhất.

Ví dụ:

```text
task.created
task.transitioned
task.completed
task.failed
workflow.created
workflow.started
workflow.completed
step.ready
step.claimed
step.dispatched
step.started
step.completed
step.failed
execution.heartbeat
execution.lost
permission.requested
permission.granted
permission.denied
provider.request.started
provider.response.delta
provider.response.completed
provider.request.failed
artifact.created
system.error
```

Loại bỏ namespace trùng như:

```text
orchestration.task.created
TaskCreatedDomainEvent
task_created
```

## 7.2 Event envelope

```python
class EventEnvelope(BaseModel):
    event_id: EventId
    event_type: EventName
    schema_version: int
    stream_id: str
    aggregate_id: str | None
    aggregate_type: str | None
    sequence: int
    occurred_at: datetime
    recorded_at: datetime | None
    session_id: SessionId | None
    correlation_id: str | None
    causation_id: EventId | None
    trace_id: str | None
    payload: EventPayload
    metadata: EventMetadata
```

## 7.3 Sequence semantics

* Sequence được cấp bởi durable event store.
* Unique constraint:

```text
UNIQUE(stream_id, sequence)
UNIQUE(event_id)
```

* Không dùng dictionary RAM làm authoritative counter.
* Không broadcast nếu persistence hoặc outbox commit thất bại.
* Multi-replica phải cho cùng một stream sequence nhất quán.

Event bus legacy hiện vẫn broadcast sau khi persistence hook lỗi, vì exception chỉ được log.

## 7.4 Compatibility

Legacy conversion chỉ được đặt tại:

```text
apps/api/windagent_api/adapters/
apps/backend/compatibility/
apps/web event client boundary
```

Không giữ compatibility mapper trong `windagent_core`.

Sau cutover:

```text
core/windagent_core/adapters/legacy_mappers.py
core/windagent_core/events/compatibility.py
```

phải được xóa hoặc chuyển ra edge adapter.

---

# 8. Error architecture

## 8.1 Canonical base error

```python
class WindAgentError(Exception):
    code: ErrorCode
    category: ErrorCategory
    retryable: bool
    safe_message: str
    details: ErrorDetails
    cause_type: str | None
```

## 8.2 Error groups

```text
DomainError
ValidationError
IdentityValidationError
InvalidStateTransitionError
ConcurrencyConflictError
NotFoundError
PermissionDeniedError
ApprovalRequiredError
ExecutionError
RuntimeLostError
ProviderError
RateLimitError
QuotaExhaustedError
AuthenticationError
TimeoutError
ToolError
SerializationError
IntegrityError
ConfigurationError
```

## 8.3 Provider migration

`ProviderFailure` không còn là root exception độc lập.

Các provider-specific error có thể tiếp tục tồn tại, nhưng phải kế thừa canonical core error:

```python
class RateLimitFailure(core.RateLimitError):
    ...
```

Retry policy chỉ được đọc:

```text
error.retryable
error.code
error.category
```

Không string-match message và không phụ thuộc trực tiếp vào provider package.

---

# 9. Config architecture

## 9.1 Immutable models

Tất cả config model:

```python
model_config = ConfigDict(
    frozen=True,
    extra="forbid",
    validate_assignment=True,
)
```

Các config chính:

```text
ApplicationConfig
DatabaseConfig
ExecutionConfig
ProviderRoutingConfig
SecurityConfig
ObservabilityConfig
FeatureGateConfig
```

## 9.2 Loader placement

Environment/file loading chuyển tới:

```text
apps/api/windagent_api/bootstrap/config_loader.py
apps/worker/windagent_worker/bootstrap/config_loader.py
apps/cli/windagent_cli/bootstrap/config_loader.py
```

Không đặt loader trong core.

## 9.3 Di chuyển code hiện tại

* `FeatureFlagsManager` chuyển khỏi core sang application bootstrap.
* `ShadowExecutionEngine` chuyển sang `verification`.
* Core chỉ chứa `FeatureGateConfig`.
* Destructive operation bị bỏ qua trong shadow mode phải trả `SKIPPED`, không được trả parity success.

Hiện comparator trả `parity_matched=True` khi bỏ qua destructive operation, có thể tạo false-pass.

---

# 10. Security architecture

## Core sở hữu

```text
Principal
Role
Permission
ResourceScope
RiskLevel
ApprovalRequirement
PermissionEvaluationRequest
PermissionDecision
SecretRef
SecretName
SecretValue
SecurityAuditContext
```

## Ngoài core

```text
Fernet encryption
OS keychain
Windows Credential Manager
environment secret loader
database encryption adapter
command regex policy implementation
provider secret resolver
key rotation job
```

## Bắt buộc sửa

1. Loại bỏ production fallback đọc `key.txt`.
2. Không tự động coi giá trị không có `enc:v1:` là plaintext hợp lệ.
3. Tạo migration command riêng:

```text
windagent security migrate-plaintext-secrets
```

4. Migration phải:

   * Dry-run mặc định.
   * Ghi audit receipt.
   * Không log plaintext.
   * Hỗ trợ rollback metadata.
   * Fail nếu encryption key không hợp lệ.
5. API không bao giờ trả secret hoặc ciphertext.
6. Secret phải được redacted trong:

   * Event payload.
   * Error details.
   * Logs.
   * Provider raw metadata.
   * Audit record.

---

# 11. Kế hoạch thực hiện theo phase

## Phase 0 — Baseline, inventory và architecture freeze

### Mục tiêu

Tạo bằng chứng đầy đủ trước khi sửa.

### Công việc

* Checkout commit `12ddf5f8`.
* Tạo nhánh `refactor/core-canonical-full-adoption`.
* Chạy:

  * Full Python tests.
  * Backend tests.
  * Frontend typecheck/build.
  * Architecture import checker.
* Inventory toàn repository:

  * Class model.
  * Enum trạng thái.
  * Event name.
  * Event envelope.
  * Error hierarchy.
  * Config loader.
  * Secret access.
  * Repository protocol.
* Tạo duplicate semantic map.

### Artifact

```text
artifacts/core_canonical/phase_00/
├── baseline_receipt.json
├── duplicate_model_inventory.json
├── lifecycle_inventory.json
├── event_inventory.json
├── error_inventory.json
├── config_inventory.json
├── security_inventory.json
└── dependency_graph.json
```

### Gate

Không sửa source trước khi inventory hoàn tất.

---

## Phase 1 — Canonical specification freeze

### Mục tiêu

Đóng băng schema và ownership trước implementation.

### Công việc

Tạo:

```text
docs/architecture/core-canonical-model.md
docs/architecture/core-lifecycle.md
docs/architecture/core-event-model.md
docs/architecture/core-contracts.md
docs/architecture/core-security-boundary.md
docs/architecture/core-migration-map.md
```

Mỗi duplicate model phải được gán một disposition:

```text
MOVE_TO_CORE
MAP_TO_CORE
KEEP_CONTEXT_LOCAL
REMOVE
DEPRECATE_TEMPORARILY
```

### Gate

Không có model “chưa quyết định ownership”.

---

## Phase 2 — Rebuild typed IDs và domain primitives

### Công việc

* Thay `BaseEntityId`.
* Tạo UUID ID và opaque ID riêng.
* Không cho phép invalid UUID domain ID.
* Không auto-generate trong deserializer.
* Thêm canonical JSON serialization.
* Thêm equality/hash behavior rõ ràng.
* Thêm migration identity classifier.

### Tests

* UUID round-trip.
* Opaque ID round-trip.
* Invalid UUID rejection.
* Prefix ID không được gọi UUID method.
* Missing persisted ID fail-closed.
* JSON serialization ổn định.

### Gate

100% public ID tests pass.

---

## Phase 3 — Canonical lifecycle và domain aggregate

### Công việc

* Chuyển `TaskState` vào core.
* Tạo Session, Workflow và Step lifecycle.
* Tạo transition matrix.
* Tạo aggregate invariants.
* Loại bỏ việc dùng `SessionStatus` cho Task/TaskRun.
* Chuẩn hóa terminal state.
* Chuẩn hóa timestamps UTC.
* Chuẩn hóa order/index semantics.

### Tests

* Mọi legal transition.
* Mọi illegal transition.
* Terminal-state immutability.
* Pause/resume.
* Retry transition.
* Recovery transition.
* Permission transition.
* Concurrent expected-version conflict.

### Gate

Transition coverage 100%.

---

## Phase 4 — Canonical contracts

### Công việc

* Tách contracts theo bounded interface.
* Chuyển cross-package port vào core.
* Thêm typed UoW.
* Thêm outbox contract.
* Thêm execution runtime contract.
* Thêm model gateway contract.
* Thêm permission evaluator contract.
* Loại bỏ duplicate port giữa core và orchestration.

### Gate

* Orchestration ports không định nghĩa lại shared contract.
* Storage implementation pass protocol conformance tests.
* Providers implementation pass model gateway conformance tests.

---

## Phase 5 — Canonical events

### Công việc

* Tạo canonical event name enum.
* Tạo typed payload registry.
* Chuyển event envelope sang Pydantic.
* Thêm strict deserialization.
* Không tự tạo session/event identity khi persisted input thiếu.
* Di chuyển compatibility mapper ra API edge.
* Chuyển orchestration event constants sang canonical names.
* Thêm event schema versioning.

### Migration

* Inventory tất cả historical event names.
* Tạo deterministic mapping.
* Migrate DB event rows.
* Với JSONL:

  * Không sửa file audit gốc.
  * Tạo canonical migrated copy.
  * Ghi manifest checksum.
  * Runtime không đọc legacy JSONL sau cutover.

### Gate

* Không có legacy event name trong internal publish path.
* Không có duplicate event envelope trong backend packages.
* Event replay pass với canonical copy.

---

## Phase 6 — Errors, config và security types

### Errors

* Chuyển base error sang core.
* Map provider errors.
* Map tool errors.
* Map orchestration concurrency errors.
* Chuẩn hóa safe serialization.

### Config

* Chuyển settings sang frozen Pydantic.
* Xóa environment access khỏi core.
* Chuyển feature flags ra composition root.
* Chuyển shadow comparator sang verification.

### Security

* Tạo canonical permission decision.
* Tạo secret types và secret-store contract.
* Chuyển backend permission profile result sang canonical decision.
* Giữ regex command policy ngoài core.

### Gate

* Core không import `os`, `cryptography`, `fastapi`, `sqlalchemy`.
* Error details không chứa secret.
* Permission evaluator không trả bool.

---

## Phase 7 — Storage migration

### Công việc

* Tạo mapper ORM ↔ canonical domain.
* Repository trả canonical object thay vì dictionary.
* UoW implement canonical contracts.
* Event store cấp durable sequence.
* Transactional outbox dùng canonical event envelope.
* Thêm optimistic concurrency bằng typed expected version.
* Thêm ID and state migration.

### Database migration

Tạo Alembic migration gồm:

* Canonical status constraints hoặc validation.
* Event schema version.
* Stream ID.
* Aggregate type.
* Correlation/causation fields.
* Unique event stream sequence.
* Legacy identity mapping table nếu cần.
* Secret migration metadata.
* Index cho event replay và aggregate query.

### Migration policy

* Dry-run trước.
* Backup database.
* Validate row count trước/sau.
* Unknown state fail migration.
* Unknown event type fail migration.
* Không fallback về `IDLE` hoặc `PENDING`.

### Gate

* Upgrade pass.
* Downgrade pass khi khả thi.
* Clean database bootstrap pass.
* Existing database migration pass.
* Row count và checksum khớp.

---

## Phase 8 — Orchestration adoption

### Công việc

* Xóa orchestration `TaskState`.
* Xóa orchestration workflow definition duplicate.
* Dùng core lifecycle.
* Dùng core workflow graph.
* Dùng core execution request/handle/result.
* Dùng core errors.
* Dùng core events.
* Dùng canonical repositories.
* Cập nhật dispatcher, scheduler, recovery và cancellation.
* Chuyển commands sang typed IDs và typed states.

Hiện orchestration đang định nghĩa commands bằng raw string.

### Tests

* Durable execution E2E.
* Duplicate claim.
* Stale fencing token.
* Pause versus completion race.
* Retry versus old callback race.
* Crash and restart.
* Destructive replay protection.
* Two-replica lease test.
* Transactional outbox fault injection.

### Gate

Không còn import model duplicate từ orchestration.

---

## Phase 9 — Providers và intelligence adoption

### Providers

* Chuyển request/response/stream/usage shared model sang core.
* Provider adapters nhận và trả core model.
* Provider-specific payload chỉ tồn tại trong adapter.
* Provider errors kế thừa core error.
* Secret input dùng `SecretRef`.
* Redaction dùng canonical security policy.

### Intelligence

* Model router sử dụng `CanonicalModelId`.
* Route lock sử dụng typed IDs.
* Planner trả canonical workflow definition.
* Không xây workflow schema riêng.
* Retry classification dựa trên canonical error metadata.

### Gate

* Không còn independent provider request/response root model.
* Không còn independent provider root exception.
* Tool-call and streaming parity pass trên OpenAI, Anthropic, Google và Ollama adapters.

---

## Phase 10 — Tools và security policy adoption

### Công việc

* Tool invocation/result dùng canonical model.
* Permission request dùng canonical security request.
* Command classifier trả canonical `PermissionDecision`.
* Tool error kế thừa canonical error.
* Audit metadata dùng canonical security context.
* Path scope kiểm tra bằng normalized absolute path.
* Tách policy evaluation khỏi API route.

### Gate

* Unknown action mặc định DENY.
* Destructive action không được auto-approve do missing profile.
* Autonomous profile vẫn không được vượt hard-deny rules.
* Permission event và audit record có cùng decision ID.

---

## Phase 11 — API, worker, CLI và WebSocket adoption

### API

* Pydantic request DTO ở API map vào core command/domain model.
* API không dùng core domain model trực tiếp làm transport model nếu làm lộ internal field.
* Xóa in-memory task store.
* Xóa mock event endpoint khỏi production route.
* Không hard-code timestamp.
* Domain error map ổn định sang HTTP response.

### Worker

* Dùng canonical execution contracts.
* Dùng typed worker/runtime IDs.
* Dùng canonical lifecycle transition.
* Dùng canonical event publishing.

### CLI

* Doctor command kiểm tra:

  * Duplicate model.
  * Import boundary.
  * Migration status.
  * Secret configuration.
  * Event schema version.

### WebSocket

* Internal event canonical.
* Chỉ serializer edge chuyển thành legacy shape khi compatibility flag còn bật.
* Client mới dùng canonical V2 event shape.
* Sequence đến từ durable store.

### Gate

* API contract tests pass.
* WebSocket reconnect/replay pass.
* Worker restart pass.
* CLI smoke pass.
* Không còn `IN_MEMORY_TASKS` hoặc `MOCK_DOMAIN_EVENTS` trong production code.

---

## Phase 12 — Compatibility removal và duplicate deletion

### Công việc

Chạy AST-based duplicate checker và xóa:

* Duplicate workflow definition.
* Duplicate lifecycle enums.
* Duplicate event envelope.
* Duplicate event catalog.
* Duplicate provider request/response.
* Duplicate permission decision.
* Duplicate error root.
* Legacy core adapters.
* Legacy config behavior.
* Legacy security plaintext fallback.

Compatibility code chỉ được tồn tại tại API edge và phải có:

```text
owner
removal date
feature flag
usage telemetry
test coverage
```

### Gate

```text
duplicate_canonical_models = 0
duplicate_lifecycle_enums = 0
duplicate_event_envelopes = 0
duplicate_root_errors = 0
internal_legacy_event_imports = 0
```

---

## Phase 13 — Full verification

### Test matrix

#### Core

* Unit tests.
* Serialization.
* Invariants.
* Transition coverage.
* Protocol conformance.
* Secret redaction.

#### Storage

* Migration.
* Repository mappings.
* Optimistic concurrency.
* Outbox atomicity.
* Event sequencing.

#### Orchestration

* Dispatch.
* Retry.
* Cancellation.
* Recovery.
* Multi-process fencing.
* Crash/resume.

#### Providers

* Sync completion.
* Streaming.
* Tool calls.
* Failover.
* 429 handling.
* Timeout.
* Secret redaction.

#### API/Worker

* REST.
* WebSocket.
* Worker lifecycle.
* Clean startup.
* Restart recovery.

#### Cross-platform

```text
ubuntu-latest
windows-latest
```

### Required commands

```text
uv sync --all-packages
uv run pytest
uv run pytest apps/backend/tests
uv run python scripts/check_architecture_boundaries.py
uv run python scripts/check_duplicate_canonical_models.py
uv run python scripts/check_event_taxonomy.py
uv run python scripts/check_secret_exposure.py
npm run typecheck
npm run build
```

---

## Phase 14 — Production cutover

### Preconditions

* Final SHA clean.
* CI gắn trực tiếp với final SHA.
* Database backup verified.
* Migration rehearsal pass trên production-like copy.
* Rollback rehearsed.
* Full E2E live Hermes execution pass.
* Event replay pass.
* Zero duplicate canonical model.
* Zero forbidden core import.
* Zero plaintext provider secret.
* No compatibility traffic ngoài API edge.

### Cutover process

1. Disable write traffic.
2. Backup database và event artifacts.
3. Chạy migration dry-run.
4. Chạy migration thực.
5. Start một backend replica.
6. Chạy smoke test.
7. Start worker.
8. Chạy execution E2E.
9. Start các replica còn lại.
10. Mở write traffic.
11. Theo dõi:

    * Event sequence conflict.
    * Optimistic concurrency conflict.
    * Runtime lost.
    * Provider error rate.
    * Permission decision mismatch.
    * Secret redaction failure.
12. Rollback ngay khi vi phạm invariant.

---

# 12. Commit strategy

Mỗi phase phải có commit riêng:

```text
chore(core): capture canonicalization baseline
docs(core): freeze canonical shared-kernel specification
refactor(core): introduce hybrid typed identifiers
refactor(core): centralize lifecycle and invariants
refactor(core): consolidate shared contracts
refactor(core): establish canonical event model
refactor(core): unify errors config and security types
refactor(storage): adopt canonical core contracts
refactor(orchestration): adopt canonical domain and lifecycle
refactor(providers): adopt canonical model contracts
refactor(tools): adopt canonical security decisions
refactor(apps): migrate api worker cli and websocket
refactor(core): remove duplicate and legacy models
test(core): add full canonical adoption verification
chore(core): finalize production cutover artifacts
```

Không squash trong khi triển khai. Chỉ squash khi merge nếu toàn bộ phase receipt đã được lưu.

---

# 13. Artifact bắt buộc

```text
artifacts/core_canonical/
├── phase_00/
├── phase_01/
├── phase_02/
├── phase_03/
├── phase_04/
├── phase_05/
├── phase_06/
├── phase_07/
├── phase_08/
├── phase_09/
├── phase_10/
├── phase_11/
├── phase_12/
├── phase_13/
├── phase_14/
└── final/
    ├── final_verdict.json
    ├── changed_files.json
    ├── migration_report.json
    ├── duplicate_model_report.json
    ├── architecture_boundary_report.json
    ├── event_taxonomy_report.json
    ├── lifecycle_coverage_report.json
    ├── secret_security_report.json
    ├── test_receipt.json
    ├── ci_receipt.json
    └── rollback_receipt.json
```

---

# 14. Final acceptance criteria

Chỉ được công nhận hoàn tất khi tất cả điều kiện sau đạt:

## Core

* Core chỉ phụ thuộc Pydantic và typing support đã phê duyệt.
* Không có framework hoặc infrastructure import.
* 100% public model type-annotated.
* Config immutable.
* Security không chứa encryption implementation.
* Lifecycle và transition matrix có một nguồn duy nhất.

## Repository

* Orchestration dùng canonical lifecycle.
* Providers dùng canonical request/response.
* Storage trả canonical domain object.
* Tools dùng canonical permission decision.
* API và worker không giữ canonical duplicate.
* Không còn runtime mapper fail-open.
* Không còn tự sinh ID khi deserializing persisted input.
* Không còn unknown status fallback.
* Không còn legacy event name trong internal event path.

## Data

* Database migration pass.
* Event migration pass.
* Identity migration pass.
* Không mất row.
* Không mất event.
* Sequence nhất quán.
* Rollback rehearsal pass.

## Security

* Không đọc production secret từ `key.txt`.
* Không tự động chấp nhận plaintext legacy.
* Không log plaintext, ciphertext hoặc raw provider token.
* Secret migration có audit receipt.

## Verification

* Full Python tests pass.
* Backend tests pass.
* Frontend typecheck và build pass.
* Windows và Ubuntu CI pass.
* Clean-clone E2E pass.
* Live runtime execution pass.
* Crash/recovery pass.
* Multi-replica fencing pass.

---

# 15. Final verdict policy

Không được phát hành verdict `CORE_CANONICAL_FULL_ADOPTION_VERIFIED` nếu chỉ package core pass test.

Các verdict hợp lệ:

```text
CORE_CANONICAL_IMPLEMENTATION_IN_PROGRESS
CORE_CANONICAL_MIGRATION_BLOCKED
CORE_CANONICAL_ADOPTION_PARTIAL
CORE_CANONICAL_VERIFIED_READY_FOR_STAGING
CORE_CANONICAL_FULL_ADOPTION_VERIFIED
```

Verdict cuối chỉ được dùng khi:

```text
duplicate canonical model count = 0
migration gates = passed
consumer adoption gates = passed
live runtime gates = passed
CI attached to final SHA = passed
```
