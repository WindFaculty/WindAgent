# KẾ HOẠCH HOÀN THIỆN WINDAGENT ARCHITECTURE V2

## 1. Phạm vi và quyết định đã khóa

### Repository

* Repository: `WindFaculty/WindAgent`
* Commit đã audit: `28d7fa1be11bbea954ee0977ee0252e2faabd1c7`
* Điểm bắt đầu: **HEAD mới nhất của nhánh đang chứa commit trên**
* Không sửa trực tiếp branch gốc.
* Tạo branch mới:

```text
fix/architecture-v2-real-cutover
```

### Quyết định kiến trúc

| Hạng mục                       | Quyết định                                 |
| ------------------------------ | ------------------------------------------ |
| Điểm bắt đầu                   | HEAD mới nhất của branch chứa commit       |
| `apps/backend`                 | Staged cutover rồi mới xóa                 |
| API và Worker                  | Hai process độc lập                        |
| Event bus                      | SQL transactional outbox                   |
| Plugins                        | Package top-level độc lập                  |
| Skills                         | Package top-level độc lập                  |
| Canonical Provider/Tool models | Chuyển ngay, không compatibility re-export |
| API V1                         | Loại bỏ ngay                               |
| CI                             | Windows-only                               |
| Cutover verdict                | Phải đạt đủ toàn bộ acceptance gate        |

### Giả định bắt buộc

Mặc dù API V1 bị loại bỏ ngay, dữ liệu hiện tại vẫn phải được bảo toàn:

* Không xóa database người dùng.
* Không reset schema.
* Không thay đổi ID hiện hữu.
* Mọi migration phải có `upgrade`, `downgrade` và kiểm thử rollback.
* Nếu schema cũ không thể ánh xạ an toàn, execution phải dừng với verdict `BLOCKED_DATA_MIGRATION`, không được âm thầm bỏ dữ liệu.

---

# 2. Mục tiêu cuối cùng

Cấu trúc canonical sau cutover:

```text
wind-agent/
├── apps/
│   ├── api/
│   ├── cli/
│   ├── web/
│   ├── worker/
│   ├── desktop/
│   └── backend/          # Chỉ tồn tại tạm thời trong migration
│
├── core/
│   ├── domain/
│   ├── contracts/
│   │   ├── providers/
│   │   └── tools/
│   ├── events/
│   ├── errors/
│   ├── config/
│   └── security/
│
├── orchestration/
├── intelligence/
├── providers/
├── tools/
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

Dependency direction chuẩn:

```text
apps
  ↓
application/platform modules
  ↓
core contracts/domain
```

Không được phép:

```text
apps/api       → apps/worker
apps/worker    → apps/api
apps/desktop   → Python implementation internals
core           → infrastructure packages
providers      → intelligence
tools          → orchestration
storage        → provider implementation
```

Hiện tại API đang import trực tiếp Worker trong composition root, trong khi `windagent-worker` không được khai báo là dependency của API. Đây là lỗi P0 cần xử lý đầu tiên.

---

# 3. Nguyên tắc thực hiện

## Fail-closed

Mọi phase phải kết thúc bằng một trong các verdict:

```text
PASS
BLOCKED
FAILED
INVALID_RUN
```

Không được dùng:

```text
MOSTLY_PASS
PASS_WITH_KNOWN_ISSUES
TEMPORARY_PASS
```

## Không được làm giả production readiness

Cấm:

* Mock service trong production composition root.
* Health check luôn trả `UP`.
* Fallback database tự động trong production.
* Placeholder implementation có method rỗng.
* Hardcoded worker heartbeat.
* Hardcoded migration revision.
* Hardcoded pending outbox bằng 0.
* Architecture checker tính condition nhưng không emit violation.

## Mỗi phase phải tạo evidence

```text
artifacts/architecture_v2_real_cutover/
├── phase_00/
├── phase_01/
├── ...
└── final/
```

Mỗi phase tối thiểu có:

* `execution_receipt.json`
* `changed_files.txt`
* `test_results.json`
* `risk_register.md`
* `phase_verdict.md`

---

# 4. PHASE 0 — Khóa baseline và xác minh repository

## Mục tiêu

Tạo baseline chính xác trước khi thay đổi code.

## Công việc

1. Xác định branch chứa commit `28d7fa1...`.
2. Checkout HEAD mới nhất của branch đó.
3. Ghi nhận:

   * Starting branch
   * Starting SHA
   * Remote SHA
   * Worktree status
   * Existing stashes
   * Existing untracked files
4. Tạo branch:

```powershell
git switch -c fix/architecture-v2-real-cutover
```

5. Không pop hoặc xóa stash.
6. Chạy toàn bộ test hiện hữu trước refactor.
7. Chạy:

   * Python package imports
   * Backend tests
   * API tests
   * Worker tests
   * CLI tests
   * Desktop type-check
   * Web type-check
   * Desktop build
   * Web build
8. Lưu baseline dependency graph.

## Gate

```text
BASELINE_VALID
```

Nếu baseline đang lỗi, không được quy lỗi cho cutover. Phải lập danh sách lỗi có sẵn.

---

# 5. PHASE 1 — Sửa architecture specification và checker

Phần này thực hiện các mục 1, 2 và 16 trong danh sách sửa.

## 5.1 Tạo dependency policy canonical

Thay `scaffold_v2.yaml` bằng một policy machine-readable rõ ràng:

```yaml
packages:
  core:
    layer: domain
    allowed_dependencies: []

  providers:
    layer: infrastructure
    allowed_dependencies:
      - core

  api:
    layer: application
    allowed_dependencies:
      - core
      - orchestration
      - intelligence
      - providers
      - tools
      - workflows
      - verification
      - context
      - memory
      - execution
      - storage
      - observability
      - evals
      - plugins
      - skills
```

Thêm rule:

```yaml
global_rules:
  forbid_cross_app_imports: true
  forbid_core_framework_imports: true
  require_declared_workspace_dependencies: true
  forbid_dependency_cycles: true
```

## 5.2 Sửa architecture checker

Hiện checker tính dependency không được phép nhưng chỉ chạy `pass`, nên không phát sinh violation.

Phải sửa thành violation thật:

```python
if target_dependency not in allowed_dependencies:
    violations.append(...)
```

Checker mới phải kiểm tra:

1. Import dependency có được phép hay không.
2. Dependency có khai báo trong `pyproject.toml`.
3. Cross-app dependency.
4. Circular dependency.
5. Forbidden framework trong core.
6. Public API leakage.
7. Duplicate canonical models.
8. Namespace/path consistency.
9. Workspace member completeness.
10. Package version metadata consistency.
11. Top-level Plugins và Skills tồn tại.
12. Legacy backend không được import bởi package V2.

## 5.3 Sửa scaffold checker

Không được dùng file hiện tại làm expected content.

Expected state phải được sinh hoàn toàn từ config canonical.

Thay logic:

```python
if file.exists():
    return file.read_text()
```

bằng generator deterministic.

## Test bắt buộc

Tạo fixture cố tình vi phạm:

* API import Worker.
* Providers import Intelligence.
* Core import SQLAlchemy.
* Package import dependency chưa khai báo.
* Circular dependency.
* Sai namespace.
* Thiếu package.
* Duplicate model.

Mỗi fixture phải khiến checker trả exit code khác 0.

## Gate

```text
ARCHITECTURE_POLICY_ENFORCED
```

---

# 6. PHASE 2 — Loại bỏ dependency API → Worker

Thực hiện mục 1 và 14.

## Công việc

Xóa hoàn toàn:

```python
from windagent_worker.runner import ProductionWorker
```

khỏi `apps/api`.

API không được:

* Import Worker.
* Khởi động Worker.
* Dừng Worker.
* Truy cập Worker object trong memory.
* Gọi method Worker trực tiếp.

## Thiết kế thay thế

Tạo contract trong Core:

```text
core/windagent_core/contracts/workers/
├── __init__.py
├── control.py
├── heartbeat.py
└── models.py
```

Các port đề xuất:

```python
class WorkerHeartbeatRepository(Protocol):
    async def get_active_workers(self, stale_after_seconds: int): ...

class WorkSubmissionPort(Protocol):
    async def submit(self, request: WorkSubmission): ...

class WorkerStatusQueryPort(Protocol):
    async def get_status(self): ...
```

API chỉ sử dụng các port này qua Storage hoặc Orchestration.

Worker tự chạy độc lập:

```powershell
uv run --package windagent-worker python -m windagent_worker
```

API tự chạy độc lập:

```powershell
uv run --package windagent-api uvicorn windagent_api.main:app
```

## Test bắt buộc

1. Cài API package mà không cài Worker package.
2. Import API thành công.
3. Khởi động API khi Worker chưa chạy.
4. Readiness phản ánh Worker unavailable theo đúng profile.
5. Cài Worker package mà không cài API.
6. Worker khởi động và poll queue bình thường.
7. Architecture graph không còn edge `api -> worker`.

## Gate

```text
API_WORKER_PROCESS_BOUNDARY_ENFORCED
```

---

# 7. PHASE 3 — Transactional Outbox và Event Publisher thật

Thực hiện mục 4 và 5.

## Thành phần cần xây dựng

```text
storage/windagent_storage/outbox/
├── models.py
├── repository.py
├── sql_repository.py
└── migrations/

observability/windagent_observability/events/
├── publisher.py
├── dispatcher.py
├── retry.py
└── dead_letter.py
```

## Outbox record

Tối thiểu gồm:

```text
event_id
aggregate_id
aggregate_type
event_type
payload
schema_version
sequence_number
created_at
available_at
published_at
attempt_count
last_error
status
deduplication_key
```

## Yêu cầu

* Domain state và outbox event phải commit trong cùng transaction.
* Publisher đọc theo batch.
* Có optimistic claim hoặc lease.
* Có retry với exponential backoff và jitter.
* Có dead-letter state.
* Có idempotency.
* Có replay.
* Có ordering theo aggregate.
* Có shutdown drain.
* Không mất event khi process crash.

## Thay MockEventBus

Xóa production usage của:

```python
class MockEventBus:
    async def publish(...):
        pass
```

Mock chỉ được tồn tại trong test package.

## Test bắt buộc

* Commit domain state nhưng publish thất bại.
* Restart publisher và publish lại.
* Duplicate dispatch.
* Concurrent publishers.
* Crash giữa claim và publish.
* Poison event.
* Ordering theo aggregate.
* Dead-letter replay.
* Transaction rollback không được tạo outbox event.

## Gate

```text
DURABLE_EVENT_PIPELINE_OPERATIONAL
```

---

# 8. PHASE 4 — Tách Plugins và Skills thành package top-level

Thực hiện mục 8.

## Cấu trúc mới

```text
plugins/
├── pyproject.toml
└── windagent_plugins/
    ├── contracts/
    ├── manifest/
    ├── registry/
    ├── loader/
    ├── lifecycle/
    ├── isolation/
    └── security/

skills/
├── pyproject.toml
└── windagent_skills/
    ├── contracts/
    ├── manifest/
    ├── registry/
    ├── loader/
    ├── versioning/
    └── execution/
```

## Migration

Di chuyển khỏi:

```text
tools/windagent_tools/plugins
tools/windagent_tools/skills
```

Không để compatibility re-export trong `windagent_tools`.

Phải cập nhật toàn bộ import ngay trong cùng phase.

## Ownership

### Plugins

Quản lý:

* Plugin manifest
* Installation
* Enable/disable
* Dependency validation
* Capability registration
* Isolation boundary
* Version compatibility
* Permission declaration

### Skills

Quản lý:

* Skill manifest
* Prompt/instruction assets
* Tool requirements
* Model requirements
* Input/output schema
* Version pinning
* Skill resolution
* Skill execution contract

### Tools

Chỉ quản lý executable tools:

* Filesystem
* Shell
* Git
* Browser
* Database
* MCP
* Testing
* AST
* LSP

## Gate

```text
PLUGIN_SKILL_BOUNDARIES_SEPARATED
```

---

# 9. PHASE 5 — Di chuyển Provider và Tool contracts trong Core

Thực hiện mục 7 và 11.

Theo quyết định đã chốt, migration diễn ra ngay và **không có compatibility re-export**.

## Cấu trúc mới

```text
core/windagent_core/contracts/providers/
├── requests.py
├── responses.py
├── usage.py
├── capabilities.py
└── ports.py

core/windagent_core/contracts/tools/
├── invocation.py
├── results.py
├── metadata.py
└── ports.py
```

## Xóa cấu trúc cũ

```text
core/windagent_core/providers/
core/windagent_core/tools/
```

## Quy tắc ownership

Core sở hữu:

* Provider request/response contract
* Tool invocation/result contract
* Ports
* Canonical identifiers
* Error taxonomy dùng chung
* Capability schema độc lập implementation

Providers sở hữu:

* HTTP transport
* Authentication
* Protocol translation
* Retry mapping
* Vendor-specific request/response
* Endpoint discovery
* Model registry implementation

Tools sở hữu:

* Tool implementation
* Sandboxing
* Permission enforcement adapter
* Execution
* Artifact production

## Duplicate-model scanner

Scanner phải phát hiện class hoặc schema canonical bị định nghĩa lại theo:

* Fully qualified semantic name
* Field signature
* JSON schema hash
* Model purpose tag

## Gate

```text
CANONICAL_CONTRACT_OWNERSHIP_UNIFIED
```

---

# 10. PHASE 6 — Chuẩn hóa Providers và loại bỏ legacy adapters

Thực hiện mục 9.

## Công việc

1. Kiểm kê:

   * V2 adapters
   * V3 adapters
   * OpenAI-compatible adapters
   * Vendor adapters
2. Chọn một canonical implementation cho:

   * OpenAI
   * Anthropic
   * Google
   * NVIDIA
   * OpenRouter
   * Mistral
   * Ollama
   * Local
3. Xóa:

   * `LegacyAnthropicAdapter`
   * `LegacyGoogleAdapter`
   * `LegacyOllamaAdapter`
   * Adapter duplicate không còn được sử dụng
4. Không dùng package version `3.0.0` để biểu thị architecture version.
5. Chuẩn hóa:

   * `package_version`
   * `architecture_version`
   * `provider_protocol_version`

## Test bắt buộc

* Import surface.
* Protocol detection.
* Test Connect.
* Same-model endpoint failover.
* 429 retry.
* Cache consistency.
* Streaming.
* Cancellation.
* Secret redaction.
* No provider import from intelligence.

## Gate

```text
PROVIDER_IMPLEMENTATION_CANONICALIZED
```

---

# 11. PHASE 7 — Hoàn thiện composition roots

Thực hiện mục 10.

Không tạo một “god container” dùng chung cho mọi process.

## API composition root

API được phép compose:

* Database
* Unit of Work
* Query services
* Command services
* Provider registry
* Tool registry
* Plugin registry
* Skill registry
* Workflow registry
* Context services
* Memory query services
* Verification query services
* Observability
* Outbox submission
* Worker status query

Không compose:

* Production Worker
* Worker event loop
* Tool subprocess runtime trực tiếp
* Desktop supervisor

## Worker composition root

Worker compose:

* Database
* Durable queue
* Lease manager
* Orchestration engine
* Execution runtime
* Tools
* Providers
* Intelligence pipeline
* Context
* Memory
* Workflows
* Verification
* Outbox publisher
* Observability

## CLI composition root

CLI compose service theo command:

* `doctor`
* `architecture-check`
* `run`
* `eval`
* `provider test`
* `worker status`

## Desktop supervisor

Desktop/Tauri chịu trách nhiệm:

* Khởi động API process.
* Khởi động Worker process.
* Theo dõi lifecycle.
* Restart policy.
* Port allocation.
* Log collection.
* Graceful shutdown.

## Gate

```text
PROCESS_SPECIFIC_COMPOSITION_COMPLETE
```

---

# 12. PHASE 8 — Loại bỏ API V1 ngay

Thực hiện quyết định 7B.

## Công việc

Xóa:

* V1 routes
* V1 compatibility router
* V1 transport DTO
* V1 route parity adapter
* V1 tests không còn giá trị
* Feature flag V1/V2
* V1 documentation
* Legacy frontend API client

Không để:

```text
/api/v1/*
```

tiếp tục hoạt động.

## Migration frontend

Cập nhật:

* `apps/web`
* `apps/desktop`
* `apps/cli`
* Integration tests
* Dev scripts
* Environment variables
* WebSocket paths

Tất cả phải dùng API V2.

## API tombstone behavior

Có thể trả rõ ràng:

```http
410 Gone
```

cho `/api/v1/*` trong một release duy nhất nếu cần chẩn đoán client cũ, nhưng không forward hoặc thực thi business logic.

Nếu chọn tombstone, nó không được tính là compatibility API.

## Gate

```text
API_V1_REMOVED
```

---

# 13. PHASE 9 — Migration dữ liệu và schema rollback

Thực hiện mục 9 trong danh sách completion và bảo toàn dữ liệu.

## Công việc

1. Chụp schema hiện tại.
2. Kiểm kê table từ legacy backend.
3. Lập source-to-target map:

   * Session
   * Task
   * Workflow
   * Run
   * Step
   * Tool call
   * Audit
   * Event
   * Provider
   * Memory
   * Permission
4. Viết Alembic migrations.
5. Không dùng `create_all()` như production migration mechanism.
6. Mỗi migration phải có downgrade.
7. Thêm schema checksum.
8. Thêm migration lock.
9. Thêm backup trước migration.
10. Thêm post-migration reconciliation.

## Kiểm thử dữ liệu

Tạo fixture database có:

* Session đang chạy.
* Workflow đang pause.
* Failed task.
* Completed task.
* Outbox pending.
* Provider configuration.
* Audit records.
* Unicode data.
* Large payload.
* Foreign-key relationships.

Sau migration phải bảo toàn:

* Row count
* IDs
* Relationships
* Timestamps
* Status
* Payload hashes
* Audit history

## Gate

```text
DATA_MIGRATION_AND_ROLLBACK_PROVEN
```

---

# 14. PHASE 10 — Readiness, liveness và diagnostics thật

Thực hiện mục 5.

## Liveness

Chỉ xác nhận process event loop còn sống.

```text
/health/live
```

Không kiểm tra external dependencies.

## Readiness

```text
/health/ready
```

Phải kiểm tra thật:

* Database connection
* Current schema revision
* Outbox publisher heartbeat
* Queue access
* Worker heartbeat
* Provider registry loaded
* Tool registry loaded
* Plugin registry loaded
* Skill registry loaded
* Workflow registry loaded
* Event dispatcher active
* Required filesystem paths
* Configuration validity

## Trạng thái

```text
UP
DEGRADED
DOWN
NOT_REQUIRED
```

## Profile

### Production

Fail-closed.

### Development

Có thể cho phép Worker chưa chạy, nhưng phải trả:

```text
DEGRADED
```

không được trả `UP`.

### Test

Cho phép in-memory adapter khi được inject rõ ràng.

Không được tự fallback vì thiếu container.

## Doctor command

`windagent doctor` phải dùng cùng health provider với API, không tạo hardcoded kết quả riêng.

## Gate

```text
HEALTH_AND_DIAGNOSTICS_TRUSTWORTHY
```

---

# 15. PHASE 11 — Staged cutover khỏi `apps/backend`

Thực hiện mục 6, 7 và 13.

## Giai đoạn 11A — Freeze

* Đánh dấu `apps/backend` là deprecated.
* Cấm thêm feature.
* Chỉ sửa security hoặc migration blocker.
* Architecture checker cấm package V2 import backend.
* Thêm ownership file.

## Giai đoạn 11B — Route inventory

Kiểm kê toàn bộ:

* REST endpoints
* WebSocket endpoints
* Event protocol
* Desktop-specific routes
* Authentication
* Permission behavior
* Upload/download
* Session lifecycle
* Workflow controls
* Agent-S3 integration
* GUI execution endpoints

## Giai đoạn 11C — Parity implementation

Di chuyển chức năng cần thiết vào:

* API
* Worker
* Execution
* Tools
* Intelligence
* Storage
* Observability

Không sao chép business logic sang API router.

## Giai đoạn 11D — Switch clients

Chuyển:

* Desktop proxy
* Web proxy
* PowerShell scripts
* Healthcheck
* Tauri supervisor
* CLI
* Test fixtures

sang API V2 và Worker V2.

## Giai đoạn 11E — Quarantine

Đổi tên tạm:

```text
apps/backend
→ legacy/apps_backend_snapshot
```

hoặc tạo archive tag trước khi xóa.

Không nằm trong:

* Python path
* Workspace
* Test discovery
* Production scripts
* Package build
* Desktop bundle

## Giai đoạn 11F — Delete

Sau khi parity và clean-clone pass:

* Xóa backend cũ.
* Xóa legacy dependencies.
* Xóa legacy tests.
* Xóa legacy scripts.
* Xóa legacy database bootstrap.
* Xóa legacy documentation.

## Gate

```text
LEGACY_BACKEND_REMOVED_FROM_PRODUCTION_PATH
```

---

# 16. PHASE 12 — Clean-clone Windows CI

Thực hiện mục 12 và 13.

Theo quyết định đã chốt, chỉ dùng Windows CI.

## Job 1 — Architecture

```text
architecture-policy
scaffold-check
dependency-graph
duplicate-model-check
cycle-check
public-api-check
```

## Job 2 — Python packages

Cài package theo nhóm và độc lập:

* core
* storage
* orchestration
* providers
* tools
* workflows
* verification
* context
* memory
* execution
* observability
* evals
* plugins
* skills
* intelligence
* api
* worker
* cli

## Job 3 — Unit tests

Chạy test từng package.

## Job 4 — Integration

* API + SQLite
* Worker + SQLite
* API + Worker
* Outbox
* Migration
* Recovery
* Provider mock server
* Tool sandbox

## Job 5 — Web

* Install
* Type-check
* Lint
* Unit test
* Build

## Job 6 — Desktop

* Install
* Type-check
* Unit test
* Frontend build
* Tauri build nếu runner hỗ trợ đầy đủ Rust/MSVC
* Sidecar process smoke test

## Job 7 — Clean-clone E2E

Từ repository mới clone:

1. Cài dependencies.
2. Migrate database.
3. Start API.
4. Start Worker.
5. Create session.
6. Submit task.
7. Worker lease task.
8. Execute mock-safe workflow.
9. Publish events.
10. Query result.
11. Graceful shutdown.

## Gate

```text
WINDOWS_CLEAN_CLONE_CI_PASS
```

---

# 17. PHASE 13 — Kiểm thử độc lập API và Worker

Thực hiện mục 14 và 15.

## API isolation test

Môi trường chỉ cài:

```text
windagent-api
và dependency được khai báo
```

Không có source Worker trên `PYTHONPATH`.

Phải pass:

* Import
* Startup
* Migrations
* Read operations
* Task submission
* Health
* Shutdown

## Worker isolation test

Môi trường chỉ cài:

```text
windagent-worker
và dependency được khai báo
```

Không có source API.

Phải pass:

* Import
* Startup
* Registration
* Heartbeat
* Lease
* Execution
* Result ingestion
* Outbox
* Shutdown

## Process integration

Start API và Worker thành hai subprocess khác nhau.

Xác nhận:

* Không chia sẻ global state.
* Không phụ thuộc process-local singleton.
* Restart API không làm Worker mất task.
* Restart Worker không làm API crash.
* Task đang chạy có recovery path.
* Duplicate Worker không xử lý cùng lease.

## Gate

```text
API_WORKER_INDEPENDENT_RUNTIME_PROVEN
```

---

# 18. PHASE 14 — Cập nhật documentation và operational scripts

Thực hiện mục 10.

## README mới phải mô tả

* Architecture V2 hiện tại.
* API process.
* Worker process.
* Desktop supervisor.
* Workspace packages.
* Dependency direction.
* Development startup.
* Production startup.
* Migration.
* Health.
* Recovery.
* Plugin và Skill lifecycle.
* Removal của API V1.
* Removal của backend cũ.

## Scripts

Cập nhật hoặc tạo:

```text
scripts/bootstrap.ps1
scripts/dev_api.ps1
scripts/dev_worker.ps1
scripts/dev_web.ps1
scripts/dev_desktop.ps1
scripts/doctor.ps1
scripts/migrate.ps1
scripts/rollback_migration.ps1
scripts/architecture_check.ps1
scripts/test_clean_clone.ps1
scripts/package_desktop.ps1
```

## Architecture Decision Records

Tạo ADR:

```text
ADR-001-api-worker-process-separation.md
ADR-002-sql-transactional-outbox.md
ADR-003-plugin-skill-package-separation.md
ADR-004-canonical-contract-ownership.md
ADR-005-api-v1-removal.md
ADR-006-legacy-backend-retirement.md
ADR-007-windows-only-ci.md
```

## Gate

```text
DOCUMENTATION_MATCHES_RUNTIME
```

---

# 19. PHASE 15 — Full regression, chaos và recovery verification

## Functional regression

* Session lifecycle
* Task lifecycle
* Workflow lifecycle
* Pause/resume/stop
* Retry
* Cancellation
* Provider routing
* Endpoint failover
* Tool execution
* Permission
* Plugin loading
* Skill loading
* Memory
* Context
* Verification
* Reporting

## Chaos tests

* API crash
* Worker crash
* Database temporarily locked
* Outbox publisher crash
* Provider timeout
* Provider 429
* Tool timeout
* Tool subprocess crash
* Corrupt event
* Duplicate event
* Stale lease
* Desktop supervisor restart

## Recovery expectations

* Không chạy lại destructive tool ngoài policy.
* Không double-complete step.
* Không mất terminal result.
* Không ghi state lùi.
* Không phát event sai sequence.
* Không mất audit trail.
* Không để task treo vô thời hạn.

## Performance baseline

Đo:

* API request p50/p95/p99
* Task enqueue latency
* Worker lease latency
* State transition latency
* Event publication latency
* Queue throughput
* Memory
* Startup time
* Graceful shutdown time

Performance không được giảm quá ngưỡng đã định nếu không có giải trình.

## Gate

```text
FULL_REGRESSION_AND_RECOVERY_PASS
```

---

# 20. PHASE 16 — Final cutover audit và publication receipt

Thực hiện toàn bộ tiêu chuẩn 9A.

## Acceptance checklist bắt buộc

### Architecture

* [ ] Không còn `apps/* -> apps/*`.
* [ ] Không có circular dependency.
* [ ] Không có undeclared workspace dependency.
* [ ] Core không import framework hoặc infrastructure.
* [ ] Plugins và Skills là package top-level.
* [ ] Canonical Provider/Tool models chỉ có một ownership.

### Runtime

* [ ] API chạy độc lập.
* [ ] Worker chạy độc lập.
* [ ] Desktop supervisor quản lý hai process.
* [ ] Không có production mock.
* [ ] Không có hardcoded readiness.
* [ ] SQL outbox hoạt động.
* [ ] Recovery và replay hoạt động.

### Cutover

* [ ] API V1 đã bị loại bỏ.
* [ ] Desktop dùng API V2.
* [ ] Web dùng API V2.
* [ ] CLI dùng service V2.
* [ ] Legacy backend không còn production path.
* [ ] Dữ liệu hiện tại được migration an toàn.

### Verification

* [ ] Windows clean-clone CI pass.
* [ ] Package isolation tests pass.
* [ ] Migration rollback pass.
* [ ] Chaos tests pass.
* [ ] Dependency graph đúng policy.
* [ ] Documentation đúng runtime.
* [ ] Worktree sạch.
* [ ] Remote SHA bằng local SHA.

## Final artifacts

```text
artifacts/architecture_v2_real_cutover/final/
├── final_verdict.md
├── publication_receipt.json
├── dependency_graph.json
├── dependency_policy_report.json
├── package_install_matrix.json
├── clean_clone_report.json
├── migration_report.json
├── rollback_report.json
├── health_report.json
├── outbox_recovery_report.json
├── process_isolation_report.json
├── regression_report.json
├── chaos_report.json
├── performance_report.json
├── legacy_removal_receipt.json
└── file_hash_manifest.json
```

## Final verdict hợp lệ

Chỉ được xuất:

```text
FINAL VERDICT: FULL_PLATFORM_CUTOVER_COMPLETE
```

khi tất cả gate đều pass.

Nếu còn bất kỳ blocker nào:

```text
FINAL VERDICT: FULL_PLATFORM_CUTOVER_NOT_COMPLETE
```

Không được tự hạ acceptance criteria để đạt PASS.

---

# 21. Thứ tự commit đề xuất

Mỗi phase phải tạo commit riêng, dễ review và rollback:

```text
1. chore: seal architecture v2 cutover baseline
2. fix: enforce architecture dependency policy
3. refactor: separate api and worker process boundaries
4. feat: implement transactional outbox event pipeline
5. refactor: extract plugins and skills workspace packages
6. refactor: centralize provider and tool contracts
7. refactor: remove duplicate legacy provider adapters
8. feat: complete process-specific composition roots
9. breaking: remove api v1 compatibility surface
10. feat: migrate legacy data to canonical schema
11. fix: implement fail-closed production health checks
12. refactor: cut desktop and web over to api v2
13. chore: remove legacy backend production path
14. ci: add windows clean-clone architecture pipeline
15. test: add process isolation and recovery matrix
16. docs: publish architecture v2 operational documentation
17. test: complete regression chaos and performance gates
18. chore: publish full platform cutover receipt
```

Không squash trong quá trình phát triển. Chỉ cân nhắc squash khi merge cuối cùng nếu lịch sử branch đã được lưu trong artifact.

---

# 22. Rủi ro cao nhất

## R1 — Cắt API V1 ngay

Rủi ro:

* Desktop hoặc Web còn gọi V1.
* Test fixtures dùng V1.
* WebSocket protocol cũ chưa được thay thế.

Biện pháp:

* Static search toàn repository.
* Network contract inventory.
* E2E capture trước khi xóa.
* Build clients ngay trong cùng phase.

## R2 — Không giữ compatibility import cho contracts

Rủi ro:

* Số lượng import cần sửa lớn.
* Một số dynamic imports không được static checker phát hiện.

Biện pháp:

* Ripgrep toàn workspace.
* Import-all smoke test.
* Package wheel installation test.
* Không merge phase nếu còn import cũ.

## R3 — Tách Plugins và Skills

Rủi ro:

* Circular dependency với Tools.
* Manifest dùng concrete Tool classes.
* Plugin loader biết quá nhiều implementation detail.

Biện pháp:

* Core contracts định nghĩa capability/registration port.
* Plugins và Skills không import app hoặc orchestration.
* Tool registry được inject qua port.

## R4 — Migration database

Rủi ro:

* Dữ liệu cũ không nhất quán.
* Enum trạng thái không tương thích.
* Workflow đang chạy bị mất recovery state.

Biện pháp:

* Preflight audit.
* Backup bắt buộc.
* Reconciliation.
* Dry-run migration.
* Rollback test.
* Block destructive migration.

## R5 — Windows-only CI

Rủi ro:

* Không phát hiện portability issue.

Biện pháp:

* Tạm thời chấp nhận do sản phẩm Windows-first.
* Không viết path logic phụ thuộc ổ đĩa cứng.
* Dùng `pathlib`.
* Có thể bổ sung Linux CI sau khi cutover ổn định.

---

# 23. Definition of Done cuối cùng

Công việc chỉ hoàn tất khi một máy Windows sạch có thể:

1. Clone repository.
2. Cài dependencies.
3. Chạy architecture checker.
4. Migrate database.
5. Start API.
6. Start Worker.
7. Start Desktop.
8. Tạo task.
9. Worker nhận task.
10. Intelligence chọn workflow và provider.
11. Tool thực thi trong sandbox.
12. Verification kiểm tra kết quả.
13. Event được ghi transactional outbox.
14. API stream event cho Desktop.
15. Task đạt trạng thái terminal.
16. Restart API và Worker mà không mất state.
17. Rollback migration thành công trên bản sao database.
18. Chạy toàn bộ test và build thành công.
19. Không sử dụng bất kỳ code path nào từ backend legacy.
20. Dependency graph khớp tuyệt đối policy canonical.
