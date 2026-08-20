# WindAgent — Architecture V3 Optimization & Hardening Plan

## 1. Mục tiêu

Đợt này **không phát triển thêm feature mới**. Mục tiêu là đưa toàn bộ WindAgent về một kiến trúc V3 thống nhất, có dependency graph rõ ràng, một nguồn authority duy nhất cho dữ liệu, realtime contract thực, composition root gọn và worker pipeline dễ kiểm chứng.

Baseline kỹ thuật dùng để refactor là:

```text
ac61c38cdca90100a14ec0ea26c4d19c35f7caa4
```

Cần đặc biệt lưu ý: nhánh `main` trên GitHub hiện vẫn trỏ tới `7e1cd9fa...` ngày 22/07/2026, trong khi `ac61c38...` là code mới hơn đang được phân tích. Vì vậy phải xác lập source-of-truth trước khi sửa kiến trúc; không được mặc định checkout `main` rồi refactor.

Root workspace hiện vẫn tự nhận là Architecture V2 và chứa toàn bộ package API, Worker, orchestration, providers, tools, workflows, storage...

---

# 2. Nguyên tắc của đợt refactor

Không rewrite WindAgent từ đầu.

Phải giữ lại các phần đang có giá trị:

* durable SQL queue;
* lease + fencing token;
* transactional outbox;
* atomic finalization;
* SQLite WAL/local-first;
* PostgreSQL profile;
* API / Worker process separation;
* Studio SQL path đã durable;
* migration + backup guards;
* crash recovery.

Không được sửa checker chỉ để “làm xanh”.

Không được thêm dependency `tools → workflows` để hợp thức hóa cycle.

Không được thay durable storage bằng in-memory adapter.

Không được trộn refactor kiến trúc với redesign UI, Blender feature, Live Record feature hay chức năng mới.

Không được xóa legacy/dead code nếu chưa có caller/dependency evidence.

---

# 3. Kiến trúc đích

Kiến trúc V3 nên có dependency direction:

```text
                         ENTRY POINTS
                  ┌─────────┼─────────┐
                  │         │         │
                 API      Worker      CLI
                  │         │         │
                  └──── Composition ──┘
                            │
                            ▼
                  APPLICATION LAYER
        ┌────────────┬────────────┬────────────┐
        │            │            │            │
 Orchestration   Workflows   Intelligence    Skills
        │            │            │
        ├──────── Context / Memory / Verification
        │
        ▼
                  CORE / PORTS
        ┌──────────────────────────────┐
        │ Domain                      │
        │ Contracts                   │
        │ Repository Ports            │
        │ Provider Ports              │
        │ Tool Ports                  │
        │ Execution Ports             │
        │ Event contracts             │
        │ Errors / IDs / state        │
        └──────────────────────────────┘
            ▲          ▲          ▲
            │          │          │
        Storage    Providers     Tools
            │       Execution    Plugins
            └──── Infrastructure ──┘
```

Quy tắc quan trọng:

```text
Application ─X─> concrete Storage
Application ─X─> concrete Provider
Application ─X─> concrete Tool implementation

Infrastructure ─X─> Application

Core ─X─> Framework
Core ─X─> Storage
Core ─X─> Provider implementation
```

Ngoại lệ duy nhất:

```text
apps/* composition root
```

được phép nhìn cả application và infrastructure để dependency injection.

Policy hiện tại chưa đạt điều này. Ví dụ configuration đang cho phép `orchestration → storage` và `storage → providers`.

---

# 4. Phase 0 — Freeze baseline và xác lập source of truth

**Priority: P0**

Đây phải là phase đầu tiên.

### Công việc

1. Xác nhận checkout chứa chính xác commit:

```text
ac61c38cdca90100a14ec0ea26c4d19c35f7caa4
```

2. Ghi lại:

```text
HEAD SHA
branch
git status
dirty files
submodules
Python version
Node version
uv.lock hash
package-lock hash
```

3. Không merge `main` vào baseline một cách tự động.

4. Tạo nhánh chuyên biệt:

```text
refactor/architecture-v3-hardening
```

từ đúng baseline được xác nhận.

5. Chạy baseline:

```bash
uv run python scripts/check_architecture_imports.py
uv run pytest
```

và toàn bộ web/desktop test hiện có.

6. Xuất:

```text
artifacts/architecture_v3/baseline/
├── baseline.json
├── dependency-report.json
├── test-report.json
├── workspace-packages.json
├── route-inventory.json
└── git-state.txt
```

### Gate

```text
ARCH_V3_BASELINE_FROZEN
```

Không qua Phase 1 nếu chưa freeze baseline.

---

# 5. Phase 1 — Định nghĩa Architecture V3 Contract

**Priority: P0**

Hiện checker và config vẫn mang Architecture V2. `check_architecture_imports.py` cũng mặc định đọc `scaffold_v2.yaml`.

### Tạo policy V3

Nên tạo:

```text
configs/architecture/scaffold_v3.yaml
```

và sau cutover mới retire V2 policy.

### Dependency matrix mới

| Package         | Được phụ thuộc                                   |
| --------------- | ------------------------------------------------ |
| `core`          | external stdlib/type libraries tối thiểu         |
| `orchestration` | `core`                                           |
| `workflows`     | `core`, orchestration contracts nếu thật sự cần  |
| `intelligence`  | `core`, context contracts                        |
| `context`       | `core`                                           |
| `memory`        | `core`                                           |
| `verification`  | `core`                                           |
| `skills`        | `core`                                           |
| `providers`     | `core`                                           |
| `tools`         | `core`                                           |
| `execution`     | `core`                                           |
| `storage`       | `core`                                           |
| `plugins`       | `core`                                           |
| `observability` | `core`                                           |
| API             | application + infrastructure chỉ tại composition |
| Worker          | application + infrastructure chỉ tại composition |
| CLI             | application + infrastructure chỉ tại composition |

### Checker phải bắt thêm

```text
dependency cycle
undeclared dependency
framework import trong core
application → infrastructure
infrastructure → application
cross-app import
module-level mutable production store
production test fallback
legacy authority
concrete adapter construction ngoài composition root
```

### Gate

```text
ARCH_V3_POLICY_FROZEN
```

Ở phase này chưa cần zero violation. Mục tiêu là policy đúng trước, rồi mới sửa code theo policy.

---

# 6. Phase 2 — Phá toàn bộ dependency cycle

**Priority: P0**

Cycle rõ nhất hiện tại:

```text
tools → workflows → tools
```

`capture/base.py` trong tools đang import `Resolution` và `Scene` từ workflows.

Trong khi `workflows` đã khai báo phụ thuộc `windagent-tools`.

### Refactor

Di chuyển các type trung lập:

```text
Scene
Resolution
TakeConfig-related contracts
Video media contracts
Capture contracts
render request/result contracts
```

khỏi:

```text
workflows/windagent_workflows/code_video/contracts*
```

sang:

```text
core/windagent_core/contracts/code_video/
```

hoặc:

```text
core/windagent_core/contracts/media/
```

Sau đó:

```text
tools ────────┐
              ▼
             core
              ▲
              │
workflows ────┘
```

### Sau đó scan toàn workspace

Không chỉ sửa cycle đầu tiên. Tìm toàn bộ SCC — strongly connected components — trong dependency graph.

### Gate

```text
dependency_cycles = 0
undeclared_workspace_dependencies = 0
```

---

# 7. Phase 3 — Dependency Inversion toàn hệ thống

**Priority: P0**

Đây là phase quan trọng nhất của kiến trúc.

Hiện `orchestration` được policy cho phép import storage trực tiếp. `storage` còn được phép phụ thuộc providers.

Cần loại bỏ hai hướng này.

## 7.1 Repository ports

Đưa interface về core:

```text
core/contracts/repositories/
├── project_repository.py
├── episode_repository.py
├── task_repository.py
├── workflow_repository.py
├── event_store.py
├── outbox_repository.py
├── provider_registry_repository.py
├── routing_repository.py
├── asset_repository.py
└── review_repository.py
```

Application nhận:

```python
ProjectRepositoryPort
TaskRepositoryPort
EventStorePort
...
```

không nhận:

```python
SqlProjectRepository
SqlUnitOfWork
SQLAlchemy Session
```

## 7.2 Provider ports

Core định nghĩa:

```text
ModelExecutionPort
ModelRegistryPort
ProviderHealthPort
ProviderDiscoveryPort
RoutingAuditPort
```

`providers` chỉ chứa adapter ra OpenRouter, Google, Ollama, Groq...

Routing policy không nên nằm lẫn với HTTP/provider adapter.

Nên đưa policy sang:

```text
intelligence/routing/
```

hoặc một application routing module tương đương.

## 7.3 Storage không được phụ thuộc Providers

Storage chỉ biết:

```text
core models
core ports
ORM mapping
SQL
```

Không được biết implementation/provider package.

### Gate

```text
application_direct_storage_imports = 0
storage_to_provider_imports = 0
infrastructure_to_application_imports = 0
```

Ngoại trừ migration/testing infrastructure được allowlist cụ thể, không dùng broad allowlist.

---

# 8. Phase 4 — Single Authority cho toàn bộ API V3

**Priority: P0**

Đây là việc lớn nhất về persistence.

`projects.py` hiện gọi mình là canonical authority nhưng sử dụng `_PROJECTS_STORE`, `_EPISODES_STORE` và idempotency map trong RAM.

Phải inventory toàn bộ `/api/v3`.

Phân loại từng route:

```text
DURABLE
DERIVED
EPHEMERAL
DEMO
INVALID
```

Canonical API production chỉ được:

```text
DURABLE
DERIVED
```

### Thứ tự migration

#### Wave A — authority nền

```text
projects
episodes
tasks
workflows
```

#### Wave B — model system

```text
providers
models
routing
routing rules
endpoint binding
provider health history
```

#### Wave C — content production

```text
assets
reviews
world
storyboard
characters
```

#### Wave D — agents

```text
agent_definitions
agent_instances
conversations
```

### Pattern bắt buộc

```text
Router
   ↓
Application Service
   ↓
Port
   ↓
SQL Repository
   ↓
Unit of Work
```

Không:

```text
Router
   ↓
global dict
```

Seed data phải chuyển vào:

```text
tests/fixtures/
```

hoặc:

```text
demo profile
```

### Gate

```text
production_module_level_stores = 0
canonical_v3_in_memory_authorities = 0
```

Test bắt buộc:

```text
create → restart API → read
```

Dữ liệu phải còn nguyên.

---

# 9. Phase 5 — Chuẩn hóa Unit of Work và transaction boundaries

**Priority: P0**

Không để mỗi feature tự nghĩ transaction semantics.

Chuẩn hóa:

```text
Command
   ↓
UoW begin
   ↓
domain mutation
   ↓
repository writes
   ↓
event store
   ↓
outbox
   ↓
commit
```

Atomic operation quan trọng:

```text
task state
result
domain event
outbox event
lease finalization
```

phải commit cùng transaction khi nghiệp vụ yêu cầu.

Không làm giảm độ an toàn của finalization hiện tại.

### Gate

Crash injection tại từng điểm:

```text
before write
after state write
after event write
before commit
after commit
```

không được tạo split state.

---

# 10. Phase 6 — Realtime Architecture V3

**Priority: P0**

Root `/ws` hiện mới làm connected/ping/ack.

Frontend lại gửi subscription envelope và chỉ xử lý message có `event_type`.

Hai protocol hiện không tương thích.

### Canonical protocol

Client:

```json
{
  "type": "subscribe",
  "aggregate_type": "run",
  "aggregate_id": "run_123",
  "after_sequence": 71
}
```

Server:

```json
{
  "type": "subscribed",
  "aggregate_type": "run",
  "aggregate_id": "run_123",
  "cursor": 71
}
```

Event:

```json
{
  "event_id": "...",
  "event_type": "...",
  "aggregate_type": "...",
  "aggregate_id": "...",
  "sequence": 72,
  "occurred_at": "...",
  "payload": {}
}
```

### Architecture

```text
Worker transaction
      │
      └── Outbox
            │
            ▼
      Event Dispatcher
            │
            ▼
          WS Hub
            │
            ▼
        Subscribers
```

Reconnect:

```text
after_sequence
      ↓
SQL replay
      ↓
catch-up complete
      ↓
live push
```

Endpoint `/ws/conversations/{id}` hiện poll DB mỗi `0.1s`.

Sau khi WS Hub hoạt động, polling này phải được retire hoặc chỉ còn fallback rõ ràng.

### Gate

```text
WS subscription contract PASS
reconnect replay PASS
duplicate suppression PASS
sequence ordering PASS
heartbeat PASS
outbox → UI E2E PASS
```

---

# 11. Phase 7 — Tách ApplicationContainer

**Priority: P1**

`ApplicationContainer` hiện compose cả `ExecutionRuntimeRegistry` và `WorktreeContextManager`, dù docstring nói API không trực tiếp compose tool subprocess runtime.

API nên làm:

```text
HTTP
validation
application service
query
command submission
realtime
health
```

API không nên sở hữu execution runtime.

### Cấu trúc đề xuất

```text
apps/api/windagent_api/composition/
├── database.py
├── repositories.py
├── studio.py
├── projects.py
├── providers.py
├── realtime.py
├── health.py
└── container.py
```

`container.py` chỉ orchestrate composers.

Sau Phase 7:

```text
API → durable task submission
Worker → actual execution
```

### Gate

```text
API ExecutionRuntimeRegistry instances = 0
API WorktreeContextManager instances = 0
```

trừ trường hợp có ADR riêng chứng minh cần thiết.

---

# 12. Phase 8 — Tách WorkerContainer

**Priority: P1**

Worker composition hiện gom queue, Studio, routing, Blender, asset gateway, normalizer và nhiều feature flag trong cùng container.

Tách thành:

```text
apps/worker/windagent_worker/composition/
├── core.py
├── queue.py
├── providers.py
├── studio.py
├── video.py
├── assets.py
├── outbox.py
└── container.py
```

Feature flag parsing cũng không nên rải:

```python
os.getenv(...)
```

khắp bootstrap.

Tạo typed runtime configuration duy nhất:

```text
WorkerRuntimeSettings
```

và validate lúc startup.

### Gate

Worker bootstrap phải có thể trả ra manifest:

```json
{
  "studio": true,
  "provider_routing": true,
  "blender": false,
  "asset_gateway": false
}
```

Không hidden capability.

---

# 13. Phase 9 — Tách ProductionWorker execution pipeline

**Priority: P1**

`poll_and_execute_tick()` hiện chứa quá nhiều trách nhiệm.

Refactor thành:

```text
poll_and_execute_tick
        │
        ▼
     claim()
        │
     lease_guard()
        │
     prepare()
        │
     execute()
        │
     validate()
        │
     finalize()
        │
     reconcile()
        │
     release()
```

Các module:

```text
worker/pipeline/
├── claim.py
├── lease_guard.py
├── executor.py
├── result_validator.py
├── finalizer.py
└── reconciler.py
```

Tạo:

```text
TaskExecutionContext
```

chứa:

```text
task id
worker id
fencing token
attempt
runtime handle
timestamps
```

### Quy tắc

Finalizer là authority duy nhất quyết định terminal persistence.

Execution adapter không được tự commit task state.

### Gate

Mỗi stage test độc lập.

Fencing test:

```text
claim A
lease takeover B
late result A
→ REJECT
```

phải PASS.

---

# 14. Phase 10 — Chuẩn hóa Provider / Model / Routing architecture

**Priority: P1**

Sau khi persistence authority ổn định mới nối Providers Hub.

Target:

```text
Provider
    │
    ├── Endpoint
    │      ├── credentials reference
    │      ├── status
    │      └── capabilities
    │
    └── Models
           │
           └── ModelRule
```

Một model có rule riêng:

```text
OpenRouter
├── deepseek-v4 → coding
├── qwen → planning
└── gemma → review
```

Tách:

```text
Provider Adapter
Model Discovery
Health Probe
Routing Policy
Route Lock
Quota State
Audit Log
```

Frontend không quyết định connection state.

Providers UI hiện đang dùng mock data và random latency; trạng thái đó phải bị cấm trong production profile.

### Gate

```text
Add Provider
→ DB
→ encrypted credential
→ real Test Connect
→ model discovery
→ assign rule
→ Worker route
→ audit
```

E2E PASS.

---

# 15. Phase 11 — Frontend architecture cleanup

**Priority: P1**

Web và Desktop tiếp tục dùng shared application.

Frontend chỉ giữ:

```text
form state
UI state
cached query state
temporary optimistic state
```

Không giữ server authority.

Cấm trong production UI:

```text
Math.random() health
fake latency
fake connected
fake credentials valid
hardcoded provider authority
```

Tất cả backend data phải đi qua:

```text
API contracts
      ↓
client
      ↓
query/mutation layer
      ↓
feature UI
```

Realtime đi qua duy nhất:

```text
@windagent/realtime
```

Không tạo WebSocket riêng trong từng feature.

---

# 16. Phase 12 — Versioning, docs và naming cutover

**Priority: P1**

Hiện README root vẫn ghi `/api/v2/*` canonical.

API README cũng mô tả API V2.

Trong khi runtime đã trả `410 Gone` cho V2 và hướng sang V3.

Phải đồng bộ:

```text
README.md
apps/api/README.md
apps/worker/README.md
apps/desktop/README.md
pyproject descriptions
docstrings
architecture checker
configs
environment docs
API docs
```

Rename dần:

```text
OrchestrationV2Container
→ OrchestrationContainer
```

nhưng chỉ sau khi caller migration hoàn tất.

Không mass rename ở đầu roadmap.

### Gate

Search toàn repo:

```text
Architecture V2
/api/v2
Phase 7
legacy canonical
```

Mọi occurrence phải thuộc một trong:

```text
migration history
tombstone
archived document
compatibility test
```

---

# 17. Phase 13 — Dead code và legacy retirement

**Priority: P1**

Không xóa trước Phase 12.

Lập caller graph cho:

```text
apps/desktop/src/api/client.ts
old desktop pages
old V2 adapters
deprecated workflows
unused provider clients
duplicate DTOs
obsolete scripts
```

Phân loại:

```text
ACTIVE
COMPATIBILITY
TEST_ONLY
DEMO
DEAD
UNKNOWN
```

Chỉ `DEAD` có evidence mới được xóa.

`UNKNOWN` không được xóa.

Legacy quarantine phải tiếp tục fail-closed.

---

# 18. Phase 14 — Security và configuration hardening

**Priority: P1/P2**

Tập trung:

```text
API keys
provider credentials
workspace paths
subprocess execution
Tauri
WebSocket
```

Provider secret:

```text
Frontend
   │ transient
   ▼
API
   │
encrypt
   ▼
secret store / encrypted DB
```

Frontend không được nhận lại plaintext key.

Tauri hiện:

```json
"csp": null
```

Phải chuyển sang CSP cụ thể trước production desktop build.

Sidecar API/Worker có thể triển khai sau khi kiến trúc runtime đã ổn.

---

# 19. Phase 15 — Performance optimization

**Priority: P2**

Chỉ tối ưu performance sau khi authority và boundaries ổn định.

Đo:

| Metric                      | Mục tiêu kiểm soát             |
| --------------------------- | ------------------------------ |
| durable queue claim latency | regression không vượt baseline |
| enqueue p95                 | regression không vượt baseline |
| DB transaction duration     | theo command                   |
| Worker execution overhead   | tách khỏi model/tool runtime   |
| WebSocket dispatch          | đo outbox → client             |
| reconnect replay            | theo số event                  |
| SQLite lock errors          | 0 trong acceptance workload    |
| PostgreSQL contention       | không tạo duplicate claim      |
| API endpoint latency        | đo P50/P95/P99                 |

Không “optimize” bằng cách bỏ durability.

---

# 20. Phase 16 — Final architecture certification

Chạy toàn bộ:

```bash
architecture checker
ruff
pytest unit
pytest architecture
pytest contract
SQLite integration
PostgreSQL integration
API smoke
Worker recovery
queue/fencing tests
outbox tests
WebSocket replay tests
web tests
desktop tests
typecheck
build
```

Sau đó chạy các failure injections:

```text
API restart
Worker restart
worker killed during execution
DB transient failure
lease expiration
late result
duplicate command
duplicate event
WebSocket disconnect/reconnect
provider timeout
provider rate limit
```

---

# 21. Hard gates cuối cùng

| Gate                   | Điều kiện                             |
| ---------------------- | ------------------------------------- |
| `G0_SOURCE_AUTHORITY`  | baseline SHA/branch xác định          |
| `G1_DEPENDENCY_DAG`    | cycle = 0                             |
| `G2_DECLARED_DEPS`     | undeclared dependency = 0             |
| `G3_CORE_PURITY`       | framework/infra import trong core = 0 |
| `G4_LAYERING`          | application → concrete infra = 0      |
| `G5_STORAGE_INVERSION` | storage → providers = 0               |
| `G6_V3_AUTHORITY`      | canonical in-memory stores = 0        |
| `G7_DURABILITY`        | restart persistence PASS              |
| `G8_REALTIME`          | replay + push + dedup PASS            |
| `G9_API_ISOLATION`     | API không compose execution runtime   |
| `G10_WORKER_PIPELINE`  | stages tách và test được              |
| `G11_TRUTHFUL_UI`      | fake success production = 0           |
| `G12_DOCS`             | canonical docs = V3                   |
| `G13_TESTS`            | toàn bộ required suites PASS          |
| `G14_ARCH_CERTIFIED`   | architecture checker PASS             |

Final verdict duy nhất được phép:

```text
ARCHITECTURE_V3_OPTIMIZED_AND_CERTIFIED
```

---

# 22. Thứ tự triển khai thực tế

```text
Phase 0
Baseline / branch authority
     │
     ▼
Phase 1
Architecture V3 policy
     │
     ▼
Phase 2
Break dependency cycles
     │
     ▼
Phase 3
Ports + dependency inversion
     │
     ▼
Phase 4
Single V3 authority
     │
     ▼
Phase 5
Transaction/UoW
     │
     ▼
Phase 6
Realtime
     │
     ├──────────────┐
     ▼              ▼
Phase 7          Phase 8
API composition  Worker composition
     │              │
     └──────┬───────┘
            ▼
         Phase 9
      Worker pipeline
            │
            ▼
         Phase 10
 Provider/Model/Routing
            │
            ▼
         Phase 11
     Frontend boundary
            │
            ▼
     Phase 12 → Phase 13
      Docs       Cleanup
            │
            ▼
         Phase 14
      Security/config
            │
            ▼
         Phase 15
       Performance
            │
            ▼
         Phase 16
    Final certification
```

## Quy tắc dừng

Trong toàn bộ Phase 0–9:

> **Không mở rộng feature mới.**

Live Record, Blender extension, UI redesign, Browser Agent, provider UX mới và các feature production khác chỉ được tiếp tục sau khi các gate nền sau đạt PASS:

```text
G0
G1
G2
G3
G4
G5
G6
G7
G8
G9
G10
```

Kiến trúc hiện tại có nền durable khá tốt; mục tiêu của roadmap này là **không phá phần tốt**, mà loại bỏ các đường tắt V2/V3, đưa toàn bộ dependency graph về một chiều và biến API/Worker/frontend thành các vertical slice có authority rõ ràng.
