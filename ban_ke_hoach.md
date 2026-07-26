# Implementation Plan — Architecture V2 Production Hardening

## 1. Starting context

**Repository:** `WindFaculty/WindAgent`
**Starting commit:** `61d580e917adf48dc1f3dc8d56a7da70631a1293`
**Recommended branch:** `hardening/architecture-v2-production-runtime`
**Target architecture:** Architecture V2 modular monolith, API/Worker multi-process, PostgreSQL-capable multi-replica runtime.

Không triển khai trực tiếp trên `main`. Tạo branch mới chính xác từ starting commit và ghi lại:

```text
starting_sha
branch_name
git_status
workspace_package_inventory
database_schema_revision
current_test_baseline
current_architecture_report
```

## 2. Program objectives

Chương trình này xử lý bảy nhóm còn lại:

1. Persistent canonical model registry và route-lock repository.
2. Transactional Worker completion, outbox và lease release.
3. PostgreSQL multi-replica fencing và CI fail-closed.
4. Mở rộng architecture checker cho toàn repository.
5. Xây dựng web test suite và đưa web vào CI.
6. Loại bỏ dần `apps/backend`.
7. Đồng bộ version, README và authoritative verdict.

## 3. Nguyên tắc bắt buộc

* Không thay đổi public API V2 nếu không có migration contract.
* Không sử dụng in-memory state làm source of truth trong production profile.
* Không nuốt exception tại durability boundary.
* Không dùng `|| true`, `continue-on-error` hoặc test fallback trong acceptance gate.
* Mọi thay đổi schema phải có migration tiến, migration rollback và restore rehearsal.
* API và Worker phải dùng cùng persistent state.
* Missing evidence phải trả về `BLOCKED`, không được mặc định `PASS`.
* Mỗi phase phải có artifact, test receipt và commit riêng.
* Không xóa historical red artifacts; thêm authoritative pointer mới thay vì sửa lịch sử.

---

# Phase 0 — Freeze baseline and define hardening contracts

## Mục tiêu

Đóng băng trạng thái tại commit bắt đầu, tạo baseline có thể tái lập và xác định contract chính xác cho bảy phase tiếp theo.

## Công việc

### 0.1. Tạo branch

```powershell
git switch --detach 61d580e917adf48dc1f3dc8d56a7da70631a1293
git switch -c hardening/architecture-v2-production-runtime
```

Không dùng `main` làm base thay thế.

### 0.2. Ghi inventory

Thu thập:

* Workspace package list.
* Import graph.
* ORM tables và migration heads.
* API V2 route inventory.
* Worker execution flow.
* Provider registry và route-lock call sites.
* `apps/backend` production import inventory.
* CI workflow inventory.
* Web components, clients và state stores.
* Các `__version__`, package version và API version.
* Tất cả final verdict artifact hiện tại.

### 0.3. Chạy baseline

Bắt buộc chạy:

```text
Full root pytest
Architecture checker suite
API package isolation
Worker package isolation
Two-process E2E
Desktop tests
Desktop type-check
Desktop build
Web test command
Web build
Migration dry-run
Secret scan
```

Baseline kỳ vọng không thấp hơn trạng thái công bố:

```text
Backend: 726 passed, 0 failed
Architecture: 4/4
Two-process E2E: pass
Desktop: 89 passed
Web build: pass
```

Web test hiện có thể báo pass do không có test file; phải ghi rõ đây là baseline gap, không được tính là behavioral coverage.

## Artifact

```text
artifacts/architecture_v2_production_hardening/
└── phase_00/
    ├── execution_receipt.json
    ├── repository_inventory.json
    ├── database_inventory.json
    ├── route_lock_inventory.json
    ├── provider_registry_inventory.json
    ├── legacy_backend_inventory.json
    ├── frontend_inventory.json
    ├── ci_inventory.json
    ├── version_inventory.json
    ├── test_results.json
    ├── changed_files.txt
    ├── risk_register.md
    └── phase_verdict.md
```

## Acceptance gate

```text
PHASE_00_BASELINE_FROZEN
```

Chỉ pass khi baseline được chạy từ clean worktree và không có thay đổi source ngoài artifact của Phase 0.

## Commit

```text
docs(hardening): freeze architecture v2 production baseline
```

---

# Phase 1 — Persistent model registry and distributed route locks

## Vấn đề cần xử lý

`CanonicalModelRegistryService` hiện lưu canonical models, bindings và audit trail trong dictionary nội bộ. Route lock cũng là state in-process và chỉ hỗ trợ snapshot/restore thủ công. API và Worker khởi tạo các instance riêng, vì vậy chưa có shared routing authority giữa các process.

## Mục tiêu

Biến database thành source of truth cho:

* Canonical models.
* Provider endpoints.
* Endpoint/model bindings.
* Route locks.
* Route attempts.
* Explicit reselection.
* Provider routing audit trail.
* Endpoint health và cooldown cần thiết cho failover.

## 1.1. Canonical contracts

Bổ sung hoặc hoàn thiện các port trong core:

```text
CanonicalModelRepository
EndpointBindingRepository
RouteLockRepository
RouteAttemptRepository
ProviderRoutingAuditRepository
RoutingUnitOfWork
```

Các application service chỉ phụ thuộc port, không phụ thuộc SQLAlchemy ORM.

## 1.2. Database schema

Tạo hoặc chuẩn hóa các bảng:

```text
canonical_models
provider_endpoints
endpoint_model_bindings
route_locks
route_attempts
provider_routing_audit
endpoint_health_snapshots
```

### Ràng buộc bắt buộc

`canonical_models`:

```text
id primary key
canonical_name unique
family
vendor
revision
context_window
enabled
version
created_at
updated_at
```

`endpoint_model_bindings`:

```text
unique(endpoint_id, provider_model_id)
canonical_model_id foreign key
equivalence_level
confidence
active
version
```

`route_locks`:

```text
lock_id primary key
scope_type
scope_id
canonical_model_id
status
generation
version
created_at
updated_at
released_at
reselection_reason
unique active lock per scope_type + scope_id
```

`route_attempts`:

```text
attempt_id
lock_id
endpoint_id
provider_model_id
attempt_number
status
failure_category
retry_after
started_at
finished_at
```

### Database compatibility

* SQLite được phép cho local single-process development.
* PostgreSQL là authoritative backend cho multi-replica acceptance.
* Migration phải chạy được trên cả hai, hoặc phải khai báo rõ profile support.

## 1.3. Repository adapters

Triển khai trong `storage`:

```text
SqlCanonicalModelRepository
SqlEndpointBindingRepository
SqlRouteLockRepository
SqlRouteAttemptRepository
SqlProviderRoutingAuditRepository
```

Không để provider package import ORM trực tiếp.

## 1.4. Refactor services

`CanonicalModelRegistryService` nhận repository/UoW qua constructor.

Không còn production default:

```python
self._canonical_models = {}
self._bindings = {}
```

In-memory implementation chỉ được đặt tại:

```text
tests/fakes/
tests/adapters/
```

`RouteLockService` phải thực hiện atomic resolve-or-create:

```text
1. Query active lock.
2. Nếu tồn tại, trả lock hiện tại.
3. Nếu chưa tồn tại, evaluate rule.
4. Insert lock với unique constraint hoặc compare-and-swap.
5. Khi xung đột, reload lock thắng cuộc.
6. Không tạo hai active lock cho cùng scope.
```

## 1.5. Model continuity và failover

Luồng bắt buộc:

```text
First request
→ rule selects canonical model
→ persistent route lock created
→ subsequent turns reuse canonical model
→ endpoint 429/unavailable
→ create route attempt
→ choose another endpoint with exact same canonical model/revision
→ keep route lock unchanged
```

Không tự đổi canonical model khi:

* 429.
* Network timeout.
* Endpoint unavailable.
* Provider quota exhausted.

Đổi model chỉ khi có:

* Explicit reselection request.
* Policy cho phép và có audit event.
* Người dùng hoặc orchestration strategy yêu cầu rõ ràng.

## 1.6. API và Worker composition

API và Worker phải inject cùng repository adapters thông qua database URL chung.

Cấm:

```text
API registry in memory
Worker registry in memory
API route lock independent from Worker route lock
```

## Test matrix

### Unit

* Canonical normalization.
* Binding idempotency.
* Merge/split transactional behavior.
* Route lock create/reuse/release.
* Optimistic concurrency conflict.
* Explicit reselection.
* Exact-revision endpoint selection.

### Integration

* API tạo route lock, Worker đọc đúng lock.
* Worker restart vẫn giữ model.
* API restart vẫn giữ route lock.
* 100 lượt chat cùng session giữ một canonical model.
* 50 concurrent first requests chỉ tạo một active lock.
* 429 chuyển endpoint nhưng không đổi canonical model.
* Endpoint exhaustion trả typed error, không silent fallback.
* Merge/split canonical model có audit trail durable.
* Rollback transaction không tạo partial binding.

### Multi-process

Chạy ít nhất:

```text
1 API
2 Workers
1 PostgreSQL
```

Hai Worker phải nhìn thấy cùng route lock.

## Migration và rollback

Migration tiến:

* Tạo bảng.
* Backfill canonical models và bindings hiện có.
* Backfill route locks nếu có persisted snapshot.
* Chuyển feature flag sang dual-read.
* So sánh parity.
* Chuyển sang DB authoritative.

Rollback:

* Tắt DB-authoritative flag.
* Giữ bảng và dữ liệu.
* Không xóa dữ liệu vừa ghi.
* Chỉ cho phép in-memory fallback trong development/test, không phải production.

## Artifact

```text
phase_01/
├── canonical_schema_manifest.json
├── migration_receipt.json
├── rollback_receipt.json
├── registry_parity_report.json
├── route_lock_concurrency_report.json
├── process_restart_report.json
├── same_model_failover_report.json
├── test_results.json
├── risk_register.md
└── phase_verdict.md
```

## Acceptance gate

```text
PERSISTENT_PROVIDER_ROUTING_AUTHORITY_VERIFIED
```

Điều kiện:

* Không còn production in-memory model registry.
* Không còn production in-process-only route lock.
* API/Worker cùng đọc một lock.
* Concurrent creation không tạo duplicate active lock.
* 429 failover giữ nguyên canonical model.
* Migration và rollback pass.

## Commit sequence

```text
feat(core): define persistent provider routing ports
feat(storage): add canonical registry and route lock repositories
feat(providers): migrate registry and route locks to durable storage
test(providers): verify cross-process model continuity and failover
docs(hardening): record persistent routing authority verdict
```

---

# Phase 2 — Transactional Worker completion and outbox atomicity

## Vấn đề cần xử lý

Worker hiện có thể log warning khi ghi terminal state thất bại, sau đó vẫn release lease và trả `completed`. Event cũng được append vào danh sách trong RAM trước khi chứng minh đã ghi transactional outbox.

## Mục tiêu

Bảo đảm kết quả execution chỉ được coi là hoàn thành khi toàn bộ durability transaction đã commit.

## 2.1. Thiết kế transaction

Tạo application operation:

```text
FinalizeTaskExecution
```

Input:

```text
task_id
worker_id
lease_id
fencing_token
expected_task_version
execution_result
result_artifacts
terminal_event
```

Một transaction phải thực hiện:

```text
1. Validate active lease.
2. Validate fencing token và lease generation.
3. Conditional update task state/version.
4. Persist execution result.
5. Persist artifact references.
6. Insert terminal event vào event store.
7. Insert publishable event vào outbox.
8. Mark lease released/completed.
9. Commit.
```

Không được release lease trước commit.

## 2.2. Compare-and-swap

Terminal update phải có điều kiện:

```text
WHERE task_id = ?
AND state = running
AND version = expected_version
AND active_fencing_token = ?
```

Nếu row count bằng 0:

```text
STALE_RESULT_REJECTED
```

Không retry commit một late result như kết quả hợp lệ.

## 2.3. Failure semantics

Nếu một bước trong transaction lỗi:

```text
rollback toàn bộ
task không được đánh dấu completed
lease không được release thành công
outbox không được ghi partial
Worker trả retryable persistence failure
recovery có thể claim lại sau expiry
```

Không được chỉ `logger.warning` rồi tiếp tục.

## 2.4. Event emission

Refactor `emit_event()` thành hai loại:

```text
Domain event intent
Persistent event/outbox write
```

`_emitted_envelopes` chỉ được giữ như test observer hoặc diagnostics, không phải source of truth.

Terminal event bắt buộc đi qua Unit of Work.

## 2.5. Idempotency

Tạo idempotency key:

```text
task_id + attempt_id + terminal_state + fencing_generation
```

Retry cùng transaction không tạo:

* Hai task completion records.
* Hai terminal events.
* Hai outbox records.
* Hai artifact links.

## 2.6. Recovery

Khi Worker chết tại các điểm sau:

```text
sau tool execution nhưng trước DB transaction
sau task update nhưng trước outbox insert
sau outbox insert nhưng trước commit
sau commit nhưng trước ACK nội bộ
```

Recovery phải đưa hệ thống về một trong hai trạng thái:

```text
Toàn bộ transaction chưa tồn tại → retry an toàn
Toàn bộ transaction đã commit → nhận diện idempotent completion
```

## Test matrix

### Fault injection

Inject failure tại:

* Validate lease.
* Task update.
* Result persistence.
* Artifact persistence.
* Event store insert.
* Outbox insert.
* Lease release.
* Commit.
* Sau commit trước Worker acknowledgement.

### Assertions

* Không partial commit.
* Không lost terminal state.
* Không duplicate outbox.
* Không duplicate completion.
* Không release lease khi transaction rollback.
* Late result bị reject.
* Worker takeover không ghi đè kết quả mới hơn.
* Outbox replay idempotent.
* Event ordering ổn định.

## Artifact

```text
phase_02/
├── transaction_design.md
├── fault_injection_matrix.json
├── crash_point_matrix.json
├── stale_result_report.json
├── outbox_idempotency_report.json
├── recovery_report.json
├── test_results.json
├── risk_register.md
└── phase_verdict.md
```

## Acceptance gate

```text
TRANSACTIONAL_TASK_COMPLETION_VERIFIED
```

Điều kiện:

* Terminal state, result, event, outbox và lease release atomic.
* Không còn fail-open completion.
* Tất cả fault injection pass.
* Crash/restart không làm mất hoặc nhân đôi completion.

## Commit sequence

```text
feat(core): define atomic task finalization contract
feat(storage): implement transactional task finalization
refactor(worker): commit result event outbox and lease atomically
test(worker): add durability fault injection and crash recovery matrix
docs(hardening): record transactional completion verdict
```

---

# Phase 3 — PostgreSQL multi-replica fencing and fail-closed CI

## Mục tiêu

Chứng minh hệ thống hoạt động an toàn với nhiều Worker replica trên PostgreSQL và biến CI thành acceptance authority thực sự.

## 3.1. PostgreSQL profile

Bổ sung production/test PostgreSQL profile:

```text
WINDAGENT_DATABASE_URL=postgresql+asyncpg://...
```

Thêm dependency và package isolation test cho `asyncpg`.

Không thay đổi SQLite local development, nhưng phải ghi rõ:

```text
SQLite: local/single-host profile
PostgreSQL: multi-replica production profile
```

## 3.2. Atomic queue claim

Xác minh hoặc sửa `SqlDurableTaskQueue`:

```text
SELECT ... FOR UPDATE SKIP LOCKED
```

được dùng đúng trong PostgreSQL transaction.

Với SQLite, dùng implementation phù hợp riêng hoặc conditional CAS, không giả định `SKIP LOCKED` có semantics tương đương.

## 3.3. Multi-replica scenarios

Chạy ít nhất các cấu hình:

```text
1 API + 2 Workers
1 API + 4 Workers
2 API + 4 Workers
2 API + 8 Workers
```

Workload:

```text
1,000 task cơ bản
mixed priority
lease expiry
worker crash
worker restart
slow execution
duplicate submission
cancellation
429 provider failover
outbox backlog
```

## Invariants

* Mỗi task có tối đa một successful execution generation.
* Không hai Worker cùng commit một generation.
* Stale fencing token luôn bị reject.
* Expired lease có thể takeover.
* Original Worker không thể commit sau takeover.
* Route lock vẫn giữ một canonical model giữa nhiều process.
* Không mất task.
* Không duplicate terminal event.
* Không duplicate outbox publish vượt ngoài idempotency contract.

## 3.4. Sửa CI fencing workflow

Xóa hoàn toàn:

```yaml
|| true
```

Mọi fencing, replica hoặc leader test phải trả exit code thật.

Workflow hiện tại đang nuốt failure của test nhóm fencing/replica; điều này phải được coi là blocker.

## 3.5. CI matrix mới

Backend matrix:

```text
OS: ubuntu-latest, windows-latest
Python: 3.11, 3.12
Database:
  SQLite focused suite
  PostgreSQL integration/multi-replica suite
```

Các gate:

```text
ruff check toàn bộ Python workspace
ruff format --check toàn bộ Python workspace
architecture checkers
unit tests
integration tests
regression tests
migration tests
rollback tests
PostgreSQL multi-replica tests
performance regression
secret scan
package isolation
```

## 3.6. Performance guardrails

Đo:

* Queue claim p50/p95/p99.
* Lease renew p95.
* Finalization transaction p95.
* Outbox lag.
* Throughput tasks/minute.
* Duplicate claim count.
* Stale result rejection count.
* Lock contention.
* Database pool saturation.

Không hard-code kết quả benchmark. So sánh với baseline thực tế và dùng tolerance rõ ràng.

## Artifact

```text
phase_03/
├── postgres_environment_receipt.json
├── multi_replica_matrix.json
├── fencing_report.json
├── crash_takeover_report.json
├── workload_manifest.json
├── performance_report.json
├── ci_fail_closed_report.json
├── test_results.json
├── risk_register.md
└── phase_verdict.md
```

## Acceptance gate

```text
POSTGRES_MULTI_REPLICA_FENCING_VERIFIED
```

Điều kiện:

* Không có masked test.
* Tất cả multi-replica scenario pass.
* Duplicate committed execution bằng 0.
* Stale fencing commit bằng 0.
* Crash takeover pass.
* CI workflow fail thật khi cố ý inject regression.

## Commit sequence

```text
feat(storage): add postgres production database profile
fix(storage): enforce atomic postgres task claim and fencing
test(runtime): add multi-replica crash and takeover matrix
ci: make fencing and replica tests fail closed
docs(hardening): publish multi-replica verification
```

---

# Phase 4 — Repository-wide architecture enforcement

## Mục tiêu

Mở rộng architecture policy từ 16 package chính sang toàn bộ mã nguồn production.

## 4.1. Đưa plugins và skills vào package map

Bổ sung đầy đủ vào `scaffold_v2.yaml`:

```text
plugins
skills
```

Khai báo:

* Layer.
* Namespace.
* Allowed dependencies.
* Forbidden dependencies.
* Legacy source.
* External dependencies.

Không chỉ kiểm tra thư mục tồn tại.

## 4.2. Legacy quarantine policy

Khai báo `apps/backend` là vùng quarantine có policy riêng:

```text
apps/backend chỉ được import canonical V2 packages
canonical packages không được import apps/backend
legacy services không được tạo runtime authority mới
main.py chỉ được delegate sang windagent_api
```

Tạo allowlist nhỏ cho compatibility modules. Mọi file legacy ngoài allowlist import vào production entrypoint phải fail.

## 4.3. Core internal boundaries

Bổ sung rule nội bộ:

```text
core/domain không import core/config
core/domain không import core/security implementation
core/contracts không import infrastructure
core/events chỉ phụ thuộc domain/contracts/errors được cho phép
```

Mục tiêu là enforce yêu cầu tách cấu hình khỏi domain.

## 4.4. Dynamic import scanning

Bổ sung scan cho:

```python
importlib.import_module(...)
__import__(...)
plugin module strings
entry points
runtime adapter strings
```

Không cần suy luận mọi string trong repository; chỉ scan các API dynamic import đã biết.

## 4.5. Public API enforcement

Phát hiện:

* Import private module xuyên package.
* Import ORM từ application layer.
* Import FastAPI/SQLAlchemy vào core.
* Direct infrastructure construction ngoài composition roots.
* Duplicate canonical contracts.
* Production test fakes.
* Undeclared workspace dependencies.
* Dependency cycles.

## 4.6. Composition-root rule

Chỉ các vùng sau được tạo concrete adapters:

```text
apps/api/.../composition.py
apps/worker/.../composition.py
apps/cli/.../composition.py
tests/
```

Application package không được tự tạo:

```text
DatabaseManager
SqlRepository
Provider adapter
Execution runtime adapter
```

trừ khi được policy cho phép rõ ràng.

## Test matrix

Tạo fixture repository nhỏ cho từng violation:

* Cross-app import.
* Legacy reverse import.
* Core framework import.
* Dynamic legacy import.
* Private API import.
* Missing declared dependency.
* Package cycle.
* Duplicate canonical model.
* Production fake runtime.
* Domain importing config.
* Application constructing SQL adapter.

Mỗi fixture phải làm checker fail đúng rule và exit code khác 0.

## Artifact

```text
phase_04/
├── architecture_policy_v3.yaml
├── repository_import_graph.json
├── package_dependency_report.json
├── legacy_quarantine_report.json
├── dynamic_import_report.json
├── negative_fixture_results.json
├── test_results.json
├── risk_register.md
└── phase_verdict.md
```

## Acceptance gate

```text
REPOSITORY_WIDE_ARCHITECTURE_POLICY_ENFORCED
```

Điều kiện:

* Plugins và skills được scan đầy đủ.
* Legacy quarantine được enforce.
* Core internal boundaries được enforce.
* Negative fixtures đều làm checker fail.
* Toàn repository production scan có zero violation.

## Commit sequence

```text
feat(architecture): include plugins skills and legacy quarantine
feat(architecture): enforce core internal dependency boundaries
feat(architecture): detect dynamic and private cross-package imports
test(architecture): add negative policy fixture suite
docs(hardening): publish repository-wide architecture report
```

---

# Phase 5 — Web behavioral tests and complete frontend CI

## Vấn đề cần xử lý

Web hiện dùng `vitest run --passWithNoTests`, nên test command có thể pass dù không có test file.

## Mục tiêu

Xây dựng test suite thực cho `apps/web` và đưa web thành required CI gate.

## 5.1. Test foundation

Cài và cấu hình:

```text
Vitest
Testing Library
jest-dom
happy-dom hoặc jsdom
MSW hoặc deterministic HTTP mocks
```

Bỏ:

```text
--passWithNoTests
```

## 5.2. Unit tests

Bắt buộc bao phủ:

### API client

* Base URL.
* Success/error parsing.
* RFC 7807 errors.
* Abort/cancellation.
* Unauthorized.
* Retry policy.
* Timeout.

### Event stream client

* Connect.
* Reconnect.
* Resume cursor.
* Duplicate event suppression.
* Out-of-order event handling.
* Malformed event.
* Connection close.
* Backoff.

### State recovery

* Reload session.
* Restore active task.
* Recover terminal task.
* Apply replayed events.
* Ignore duplicate sequence.
* Handle missing snapshot.

### Permission client

* Pending permission.
* Approve.
* Deny.
* Timeout.
* Server error.

### Provider client

* Provider inventory.
* Test Connect.
* Model listing.
* Disabled endpoint.
* Quota/health state.

## 5.3. Component tests

Bao phủ:

* Application bootstrap.
* Loading/error/empty state.
* Session selection.
* Task submission.
* Task progress.
* Permission dialog.
* Provider status.
* Artifact display.
* Event replay after reconnect.
* API V1 410 handling nếu client cũ gọi nhầm.

## 5.4. Integration tests

Chạy app với mock server:

```text
Submit task
→ receive task accepted
→ receive streamed events
→ display progress
→ receive completion
→ display result/artifact
```

Thêm scenario:

```text
disconnect giữa task
→ reconnect
→ replay missing events
→ UI hội tụ đúng terminal state
```

## 5.5. Browser E2E

Bổ sung Playwright hoặc công cụ E2E tương đương cho ít nhất:

* Web app load.
* API health.
* Submit mock-safe task.
* Event stream.
* Permission interaction.
* Refresh recovery.
* Provider Test Connect mock.
* V1 tombstone error presentation.

## 5.6. CI frontend matrix

Tách thành:

```text
web-test
web-typecheck
web-build
web-e2e

desktop-test
desktop-typecheck
desktop-build
```

Không dùng một gate chung mơ hồ.

## Coverage gate

Đặt baseline ban đầu thực tế, sau đó yêu cầu:

```text
Statements ≥ 75%
Branches ≥ 65%
Functions ≥ 70%
Lines ≥ 75%
```

Các module critical như event replay và state recovery nên có branch coverage cao hơn.

## Artifact

```text
phase_05/
├── web_test_inventory.json
├── coverage_report.json
├── client_contract_report.json
├── reconnect_replay_report.json
├── browser_e2e_report.json
├── frontend_ci_report.json
├── test_results.json
├── risk_register.md
└── phase_verdict.md
```

## Acceptance gate

```text
WEB_BEHAVIORAL_RUNTIME_VERIFIED
```

Điều kiện:

* Có test file thực.
* Không còn `passWithNoTests`.
* Unit, integration và E2E đều pass.
* Reconnect/replay pass.
* Web test là required CI check.
* Web build và type-check pass.

## Commit sequence

```text
test(web): establish vitest and client contract coverage
test(web): cover event replay state recovery and permissions
test(web): add task execution browser e2e
ci(frontend): require web test typecheck build and e2e
docs(hardening): publish web behavioral verification
```

---

# Phase 6 — Controlled retirement of `apps/backend`

## Mục tiêu

Loại bỏ legacy implementation mà không phá desktop, scripts, tests hoặc migration compatibility.

## 6.1. Phân loại legacy inventory

Chia mọi file trong `apps/backend` thành:

```text
DELETE
MIGRATE
KEEP_TEMPORARILY
COMPATIBILITY_ONLY
HISTORICAL_TEST_ONLY
```

Không xóa theo thư mục hàng loạt trước khi xác định consumers.

## 6.2. Freeze legacy

Bổ sung checker:

* Không được thêm router mới.
* Không được thêm service mới.
* Không được thêm ORM mới.
* Không được thêm business logic mới.
* Chỉ chấp nhận sửa compatibility hoặc removal.

## 6.3. Migrate remaining consumers

Kiểm tra và chuyển:

* Desktop sidecar startup.
* PowerShell scripts.
* Test imports.
* Alembic configuration.
* Packaging.
* Developer commands.
* CI paths.
* Documentation.
* Environment variables.
* Any direct `apps.backend` imports.

Canonical targets:

```text
windagent_api
windagent_worker
windagent_cli
windagent_storage
windagent_providers
windagent_orchestration
```

## 6.4. Compatibility window

Giữ entrypoint nhỏ:

```python
from windagent_api.main import app
```

trong một release window nếu còn external launcher dùng path cũ.

Compatibility entrypoint không được:

* Đăng ký router riêng.
* Khởi tạo database riêng.
* Chạy Worker.
* Tạo provider registry riêng.
* Giữ business logic.

## 6.5. Delete legacy implementation

Sau khi import inventory bằng 0:

Xóa hoặc archive:

* Legacy routers.
* Legacy services.
* Legacy schemas trùng canonical.
* Legacy ORM trùng storage.
* Legacy workflow runner.
* Legacy provider gateway.
* Legacy orchestration.
* Legacy tests chỉ kiểm tra implementation đã xóa.

Các regression contract quan trọng phải được chuyển sang root test suite trước khi xóa.

## 6.6. Remove Python path dependency

Xóa `apps/backend` khỏi:

* Root `pythonpath`.
* Package installation.
* Runtime scripts.
* CI lint/test paths.
* Desktop sidecar configuration.

Nếu vẫn giữ compatibility package, đóng gói thành package tối thiểu riêng thay vì để toàn legacy tree trên Python path.

## 6.7. API compatibility verification

Xác minh:

* `/api/v2/*` vẫn hoạt động.
* `/api/v1/*` vẫn trả 410 theo contract.
* Desktop dùng V2.
* Web dùng V2.
* CLI không import backend.
* Worker không import backend.
* Clean install không cần `apps/backend`.

## Artifact

```text
phase_06/
├── legacy_file_classification.json
├── legacy_consumer_inventory.json
├── migrated_contract_tests.json
├── deleted_files_manifest.json
├── compatibility_shim_report.json
├── zero_legacy_import_report.json
├── clean_install_report.json
├── rollback_plan.md
├── test_results.json
├── risk_register.md
└── phase_verdict.md
```

## Rollback

Trước khi xóa:

* Tag hoặc commit checkpoint.
* Lưu deleted-file manifest.
* Có compatibility branch hoặc reversible commit.
* Không rollback database schema bằng cách mất dữ liệu.

## Acceptance gate

```text
LEGACY_BACKEND_RUNTIME_REMOVED
```

Điều kiện:

* Zero production import từ `apps/backend`.
* Zero business logic trong compatibility shim.
* API, Worker, CLI cài độc lập.
* Desktop và web smoke pass.
* Full regression pass.
* V1 tombstone contract pass.

## Commit sequence

```text
chore(legacy): freeze backend compatibility area
refactor(runtime): migrate remaining backend consumers to canonical packages
test(runtime): relocate legacy contract regressions
chore(legacy): remove evacuated backend implementations
build(workspace): remove legacy backend from runtime pythonpath
docs(hardening): publish legacy backend removal verdict
```

---

# Phase 7 — Version, documentation and verdict convergence

## Mục tiêu

Tạo một nguồn version duy nhất và một authoritative current-state record.

## 7.1. Single source of version truth

Dùng package metadata làm nguồn chính:

```python
from importlib.metadata import version

__version__ = version("windagent-core")
```

Không hard-code nhiều version khác nhau trong:

* `__init__.py`
* FastAPI app.
* CLI.
* Worker.
* Artifacts.
* README.

Quyết định rõ hai loại version:

```text
Product/API version
Architecture generation
```

Ví dụ:

```text
product_version = 0.5.0
architecture_generation = v2
provider_protocol_version = 1.0
```

Không dùng `provider version 2.0.0`, `Architecture V3 Rebuild` và `__architecture_version__ = v2` trong cùng package nếu không có định nghĩa rõ.

## 7.2. Version checker

Tạo script:

```text
scripts/check_version_consistency.py
```

Kiểm tra:

* Root workspace version.
* Package metadata.
* `__version__`.
* FastAPI OpenAPI version.
* CLI `--version`.
* Worker version.
* Desktop/web package versions nếu chủ đích đồng bộ.
* Artifact protocol versions.

## 7.3. README rewrite

README mới phải mô tả:

* Architecture V2 hiện tại.
* API/Worker/CLI separation.
* Web và Desktop.
* Package map.
* Local SQLite profile.
* PostgreSQL production profile.
* Provider routing.
* Tool execution.
* Workflow packs.
* Context/memory.
* Development commands.
* Test commands.
* Packaging.
* Migration guide.
* Legacy status.

Loại bỏ các số liệu Phase 12 và backend 338 tests đã lỗi thời.

## 7.4. Authoritative verdict pointer

Tạo:

```text
artifacts/architecture_v2_runtime_cutover/CURRENT_VERDICT.json
```

Nội dung:

```json
{
  "status": "...",
  "authoritative_artifact": "...",
  "source_commit": "...",
  "verified_commit": "...",
  "supersedes": ["..."],
  "historical_artifacts_retained": true
}
```

Historical red verdict vẫn giữ nguyên, nhưng tooling phải đọc `CURRENT_VERDICT.json`.

## 7.5. Artifact schema

Chuẩn hóa tất cả phase artifacts:

```text
protocol_version
generated_at
source_sha
verified_sha
branch
worktree_clean
commands
results
failures
warnings
artifact_hashes
verdict
```

## 7.6. Documentation validation

CI phải kiểm tra:

* README command tồn tại.
* Package path tồn tại.
* Version khớp.
* Artifact pointer trỏ tới file tồn tại.
* Current verdict source SHA có trong Git.
* Không có raw secret.
* Không có stale test count được hard-code ngoài generated section.

## Artifact

```text
phase_07/
├── version_manifest.json
├── version_consistency_report.json
├── documentation_link_report.json
├── command_validation_report.json
├── current_verdict_validation.json
├── artifact_schema_report.json
├── test_results.json
├── risk_register.md
└── phase_verdict.md
```

## Acceptance gate

```text
VERSION_DOCUMENTATION_VERDICT_CONVERGED
```

Điều kiện:

* Một nguồn version chính.
* API/CLI/Worker báo version nhất quán.
* README phản ánh Architecture V2 hiện tại.
* `CURRENT_VERDICT.json` hợp lệ.
* Historical artifact vẫn được giữ.
* Documentation CI pass.

## Commit sequence

```text
refactor(version): derive runtime versions from package metadata
build(version): add repository version consistency gate
docs(readme): document canonical architecture v2 runtime
docs(audit): add authoritative current verdict pointer
test(docs): validate commands links versions and artifact references
```

---

# Final Phase — Full production-hardening acceptance

Phase cuối không thêm feature mới. Chỉ chạy verification từ clean clone/worktree.

## Required environments

```text
Windows clean worktree
Linux clean clone
Python 3.11
Python 3.12
SQLite local profile
PostgreSQL production profile
Node.js locked install
```

## Backend gates

* Full pytest pass.
* Unit pass.
* Integration pass.
* Regression pass.
* Migration pass.
* Rollback pass.
* Restore pass.
* Package isolation pass.
* Architecture policy pass.
* Secret scan pass.
* No legacy import pass.
* Provider routing persistence pass.
* Transactional completion pass.
* PostgreSQL multi-replica pass.
* Crash recovery pass.
* Outbox replay pass.

## Frontend gates

Web:

```text
npm ci
unit tests
integration tests
coverage
type-check
build
browser E2E
```

Desktop:

```text
npm ci
tests
type-check
build
sidecar smoke
```

## Runtime E2E

Chạy đầy đủ:

```text
Web/Desktop
→ API task submission
→ persistent route lock
→ SQL queue
→ Worker claim
→ provider/tool execution
→ transactional completion
→ outbox event
→ API query/event replay
→ UI terminal state
```

Thêm:

* Worker crash.
* Worker takeover.
* API restart.
* Provider 429.
* Endpoint failover cùng model.
* Permission pause/resume.
* Cancellation.
* Event replay.
* Database reconnect.

## Final artifact

```text
artifacts/architecture_v2_production_hardening/final/
├── final_verdict.json
├── final_verdict.md
├── execution_receipt.json
├── test_matrix.json
├── architecture_report.json
├── provider_routing_report.json
├── transactional_runtime_report.json
├── multi_replica_report.json
├── frontend_report.json
├── legacy_removal_report.json
├── version_documentation_report.json
├── migration_rollback_report.json
├── security_report.json
├── performance_report.json
├── clean_clone_report.json
├── artifact_manifest.json
└── publication_receipt.json
```

## Final verdict rules

Chỉ được công bố:

```text
ARCHITECTURE_V2_PRODUCTION_HARDENING_COMPLETE
```

khi tất cả required gates pass.

Nếu một gate thiếu evidence:

```text
ARCHITECTURE_V2_PRODUCTION_HARDENING_BLOCKED
```

Nếu test fail:

```text
ARCHITECTURE_V2_PRODUCTION_HARDENING_FAILED
```

Không được dùng partial focused tests để thay thế full matrix.

---

# Dependency order

Trình tự bắt buộc:

```text
Phase 0
  ↓
Phase 1 — Persistent routing authority
  ↓
Phase 2 — Transactional completion
  ↓
Phase 3 — PostgreSQL multi-replica proof
```

Phase 4 và Phase 5 có thể chạy song song sau Phase 0:

```text
Phase 0
  ├── Phase 4 — Architecture enforcement
  └── Phase 5 — Web tests
```

Phase 6 chỉ bắt đầu khi:

```text
Phase 1 pass
Phase 2 pass
Phase 4 pass
Phase 5 pass
```

Phase 7 chạy sau khi source structure đã ổn định.

Final acceptance chạy cuối cùng.

---

# Recommended PR strategy

Sử dụng một draft PR tổng hoặc bảy PR phụ thuộc. Phương án ít rủi ro hơn:

```text
PR 1: Persistent provider routing
PR 2: Transactional Worker completion
PR 3: PostgreSQL multi-replica and CI
PR 4: Repository-wide architecture checker
PR 5: Web tests and CI
PR 6: Legacy backend retirement
PR 7: Version/docs/verdict convergence
```

Mỗi PR:

* Base trên commit đã merge gần nhất của chương trình.
* Không trộn refactor không liên quan.
* Có artifact riêng.
* Có rollback notes.
* Không merge khi required checks chưa xanh.

---

# Definition of done

Chương trình chỉ hoàn thành khi đạt đồng thời:

```text
Persistent provider registry
Persistent distributed route locks
Same-model endpoint failover
Atomic Worker terminal transaction
Transactional outbox
PostgreSQL multi-replica fencing
Fail-closed CI
Repository-wide architecture enforcement
Real web test coverage
Legacy backend runtime removed
Single version authority
Authoritative current verdict
Windows and Linux clean verification
```
