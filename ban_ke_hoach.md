Được. Với `Wind_agent_v2`, tôi khuyên **không coi đây là thư mục refactor**, mà coi nó là **một implementation mới của WindAgent**, dùng hệ thống cũ làm nguồn tham chiếu. Cách này phù hợp vì backend hiện đã ~208k LOC/18 package, orchestration và worker có nhiều logic production đáng giữ về mặt semantics, còn frontend có 23 feature và hai query layer song song.  

Mục tiêu cuối cùng:

```text
WindAgent cũ
    │
    │ specification
    │ tests
    │ behavior reference
    ▼
Wind_agent_v2
    │
    ├── clean foundation
    ├── rewritten modules
    ├── parity tests
    └── production certification
```

Không có:

```text
Wind_agent_v2
    ↓ import
WindAgent/core
WindAgent/storage
WindAgent/providers
...
```

---

# 1. Nguyên tắc migration

Mỗi file/capability cũ phải được phân loại thành một trong 5 nhóm:

| Action          | Ý nghĩa                                                    |
| --------------- | ---------------------------------------------------------- |
| `REWRITE`       | Viết lại theo architecture mới                             |
| `EXTRACT_LOGIC` | Giữ thuật toán/semantics nhưng viết implementation mới     |
| `KEEP_ASSET`    | CSS token, image, fixture, schema data tĩnh có thể giữ     |
| `ADAPT`         | Native/runtime code quá phức tạp được bọc bằng adapter mới |
| `DELETE`        | Legacy/V2/duplicate/dead code không chuyển                 |

Tôi **không khuyến nghị copy nguyên file Python/TS rồi sửa import**.

Quy trình bắt buộc cho một capability:

```text
OLD IMPLEMENTATION
       │
       ▼
Extract behavior
       │
       ▼
Define V2 contract
       │
       ▼
Rewrite implementation
       │
       ▼
Unit test
       │
       ▼
Parity test against old
       │
       ▼
Integration test
       │
       ▼
Cut over
       │
       ▼
Delete migration bridge
```

---

# 2. Cấu trúc `Wind_agent_v2` cần tạo trước

Tôi đề xuất:

```text
WindAgent/
│
├── ... WindAgent hiện tại ...
│
└── Wind_agent_v2/
    │
    ├── apps/
    │   ├── api/
    │   ├── worker/
    │   ├── scheduler/
    │   ├── cli/
    │   └── desktop/
    │
    ├── backend/
    │   └── src/
    │       └── windagent/
    │           │
    │           ├── kernel/
    │           │   ├── ids/
    │           │   ├── errors/
    │           │   ├── events/
    │           │   ├── result/
    │           │   ├── time/
    │           │   └── types/
    │           │
    │           ├── platform/
    │           │   ├── modules/
    │           │   ├── commands/
    │           │   ├── queries/
    │           │   ├── jobs/
    │           │   ├── events/
    │           │   ├── persistence/
    │           │   ├── artifacts/
    │           │   ├── realtime/
    │           │   ├── configuration/
    │           │   ├── security/
    │           │   └── observability/
    │           │
    │           └── modules/
    │               ├── identity/
    │               ├── workspace/
    │               ├── model_gateway/
    │               ├── automation/
    │               ├── agent_runtime/
    │               ├── memory/
    │               ├── studio/
    │               ├── production/
    │               ├── live_record/
    │               └── quality/
    │
    ├── frontend/
    │   ├── app/
    │   └── packages/
    │       ├── ui/
    │       ├── api-sdk/
    │       ├── realtime/
    │       └── platform/
    │
    ├── migrations/
    │
    ├── tests/
    │   ├── architecture/
    │   ├── unit/
    │   ├── contract/
    │   ├── integration/
    │   ├── parity/
    │   ├── e2e/
    │   ├── reliability/
    │   ├── security/
    │   └── performance/
    │
    ├── migration/
    │   ├── manifests/
    │   ├── importers/
    │   └── parity/
    │
    ├── deploy/
    ├── configs/
    ├── scripts/
    ├── docs/
    │   ├── architecture/
    │   ├── adr/
    │   └── migration/
    │
    ├── pyproject.toml
    ├── compose.yaml
    └── README.md
```

---

# 3. Giai đoạn A — xây nền móng hoàn toàn trước

Không chuyển Studio, Agent, Video hay Live Record trong giai đoạn này.

Đây là phần quan trọng nhất.

## PHASE 0 — Freeze WindAgent cũ

Trước khi viết V2:

```text
WindAgent old
      ↓
freeze behavioral baseline
```

Tạo:

```text
Wind_agent_v2/migration/manifests/
├── backend_inventory.yaml
├── frontend_inventory.yaml
├── api_inventory.yaml
├── database_inventory.yaml
├── event_inventory.yaml
└── migration_matrix.yaml
```

Ví dụ:

```yaml
source:
  orchestration/scheduler/priority_queue.py

target:
  backend/src/windagent/platform/jobs/postgres_queue.py

strategy:
  REWRITE

must_preserve:
  - atomic_claim
  - priority_order
  - fencing_token
  - cancellation

must_remove:
  - legacy_v2_assumptions
```

### Gate

Mọi capability hiện tại phải biết:

```text
SOURCE
TARGET
OWNER
ACTION
DEPENDENCIES
TEST ORACLE
STATUS
```

---

# 4. PHASE 1 — Repository foundation

Chỉ setup engineering infrastructure.

### Backend

```text
Python
uv
Ruff
Pyright/mypy
pytest
SQLAlchemy async
Alembic
Pydantic
FastAPI
```

Tôi sẽ nâng minimum Python lên:

```text
Python >= 3.12
```

nếu các dependency/native integration của WindAgent cho phép.

### Frontend

```text
React
TypeScript strict
Vite
TanStack Query
Zustand
Vitest
```

### CI

Ngay từ ngày đầu:

```text
lint
typecheck
unit
architecture
security
build
```

Không đợi migrate xong mới tạo CI.

### Gate

```text
uv sync             PASS
ruff check          PASS
typecheck           PASS
pytest              PASS
frontend typecheck  PASS
frontend test       PASS
```

---

# 5. PHASE 2 — Kernel

Viết mới 100%.

```text
kernel/
├── ids/
├── errors/
├── events/
├── result/
├── time/
└── types/
```

Không chuyển `core/` cũ vào đây.

`core` hiện tại có hàng trăm file và chứa nhiều domain khác nhau, nên chỉ dùng nó để xác định primitive nào thực sự generic. 

Kernel chỉ được phép chứa thứ kiểu:

```text
EntityId
CorrelationId
CausationId
ActorId

DomainError
Result[T]

DomainEvent
EventEnvelope

Clock
Money
Version
```

Architecture gate:

```text
kernel cannot import:

FastAPI
SQLAlchemy
httpx
providers
modules
apps
```

### Gate

```text
kernel dependency count ≈ minimal
domain-specific class = 0
infrastructure dependency = 0
```

---

# 6. PHASE 3 — Platform contracts

Đây mới là foundation thực sự.

Viết:

```text
platform/
├── commands/
├── queries/
├── modules/
├── jobs/
├── events/
├── persistence/
├── artifacts/
├── security/
└── observability/
```

Các abstraction cần khóa:

```python
CommandBus
QueryBus

ModuleRegistry

JobQueue
JobHandler
JobScheduler

EventBus
EventPublisher

UnitOfWork

ArtifactStore

SecretStore

PolicyEngine

Telemetry
```

Chưa có:

```text
Episode
Agent
Model
Recording
```

Platform phải hoàn toàn domain-agnostic.

---

# 7. PHASE 4 — Module Runtime

Đây là thứ giúp sau này không sửa foundation.

Contract:

```python
class ModuleManifest:
    id: str
    version: str

    commands: tuple
    queries: tuple
    jobs: tuple
    event_handlers: tuple

    routers: tuple
    migrations: tuple

    capabilities: tuple
```

Module loader:

```text
bootstrap
   ↓
discover modules
   ↓
validate manifests
   ↓
register commands
   ↓
register queries
   ↓
register jobs
   ↓
register event handlers
   ↓
register routes
```

Sau này thêm:

```text
modules/youtube_analytics/
```

không phải sửa API bootstrap.

### Architecture gate

Feature/module mới không được chỉnh:

```text
kernel/*
platform/modules/*
apps/worker/runtime/*
apps/api/bootstrap/*
```

---

# 8. PHASE 5 — Persistence V2

Không copy `storage/`.

Viết persistence mới theo contracts.

Current WindAgent đã có SQL UoW, CAS durable queue, transactional finalization và outbox — đây là các **semantics cần giữ**, không phải cấu trúc file cần giữ. 

Target:

```text
platform/persistence/
├── database.py
├── transaction.py
├── unit_of_work.py
├── health.py
└── postgres/
```

## Chỉ PostgreSQL là canonical

```text
development:
PostgreSQL

integration:
PostgreSQL

production:
PostgreSQL
```

SQLite chỉ được phép:

```text
isolated unit test
small developer experiments
```

Production gặp:

```text
sqlite://
```

thì:

```text
STARTUP_ERROR
```

WindAgent hiện còn default SQLite song song với PostgreSQL deployment; V2 không nên kế thừa drift này. 

---

# 9. Database mới không nên mang theo 31 migration cũ

WindAgent hiện có 31 Alembic revisions. 

Tôi không khuyến nghị copy:

```text
0001
...
0031
```

sang V2.

V2 tạo:

```text
0001_v2_foundation
```

sạch.

Sau đó module-specific migrations:

```text
0002_identity
0003_jobs
0004_model_gateway
0005_agent_runtime
...
```

Nếu cần dữ liệu cũ:

```text
OLD DATABASE
    │
    ▼
migration importer
    │
validate
    ▼
NEW DATABASE
```

Không dùng schema legacy làm nền.

---

# 10. PHASE 6 — Event + Outbox foundation

Viết mới:

```text
platform/events/
├── envelope.py
├── registry.py
├── dispatcher.py
├── publisher.py
├── outbox.py
└── subscriptions.py
```

Envelope:

```text
event_id
event_type
event_version

aggregate_type
aggregate_id
sequence

actor_id
correlation_id
causation_id

occurred_at
payload
```

Atomic transaction:

```text
domain change
+
outbox event
+
COMMIT
```

Pattern này hiện đã tồn tại trong WindAgent cũ và nên được giữ về semantics. 

---

# 11. PHASE 7 — Job Runtime + Worker foundation

Đây là phần phải đặc biệt cẩn thận.

Current worker đã có:

```text
claim
→ lease
→ heartbeat
→ dispatch
→ fencing validation
→ finalize
```

và retry/cancellation. 

Không copy pipeline.

Viết worker engine mới dựa trên behavior đó:

```text
apps/worker/
      ↓
WorkerRuntime
      ↓
JobQueue
      ↓
claim
      ↓
LeaseGuard
      ↓
JobHandlerRegistry
      ↓
execute
      ↓
ResultValidator
      ↓
atomic finalize
```

Job:

```python
JobEnvelope(
    id,
    type,
    version,
    payload,

    priority,
    attempt,
    max_attempts,

    timeout,
    deadline,

    correlation_id,
    causation_id,

    fencing_token,
)
```

### Reliability gate

Bắt buộc test:

```text
two workers claim same job
worker crash
lease expire
stale worker finalize
duplicate submission
retry
timeout
cancellation
server restart
worker restart
```

### Foundation milestone

Sau Phase 7, V2 phải chạy được một fake job:

```text
POST /debug/jobs
        ↓
PostgreSQL
        ↓
Worker
        ↓
FakeJobHandler
        ↓
Result
        ↓
Outbox
        ↓
WebSocket
```

**Đây là milestone quan trọng nhất.**

Chưa có Agent nhưng foundation đã production-capable.

---

# 12. PHASE 8 — API foundation

Chỉ khi foundation phía dưới ổn mới xây FastAPI.

```text
apps/api/
├── bootstrap/
├── middleware/
├── auth/
├── errors/
├── health/
└── api/
```

Router chỉ được:

```text
HTTP
 ↓
validate DTO
 ↓
CommandBus / QueryBus
 ↓
response mapper
```

Router cấm:

```text
SQL
provider calls
business logic
job implementation
```

API mới không nên kéo theo 29 router V2 hoặc dual-mount hiện tại. Current inventory vẫn còn V2 compatibility và Live Record dual mount. 

Tôi sẽ gọi API mới:

```text
/api/v4
```

hoặc một version canonical mới.

Tên thư mục `Wind_agent_v2` **không nên quyết định API version**.

---

# 13. PHASE 9 — Security foundation

Phải làm trước feature migration.

```text
Identity
Authentication
Authorization
Policy Engine
Secret Store
Audit
Rate limit
```

Tool execution:

```text
Agent
 ↓
Policy
 ├── ALLOW
 ├── DENY
 └── REQUIRE_APPROVAL
 ↓
Executor
```

Đừng migrate shell/browser trước khi Policy Engine hoàn thành.

---

# 14. PHASE 10 — Observability foundation

Mọi operation:

```text
trace_id
correlation_id
causation_id
actor_id
```

Job thêm:

```text
job_id
run_id
task_id
```

Signals:

```text
Structured logs
Metrics
Tracing
Audit events
Health
Readiness
```

Sau Phase 10 mới coi **foundation hoàn tất**.

---

# 15. Foundation V2 Definition of Done

Trước khi chuyển feature đầu tiên, V2 phải đạt:

```text
API
 ↓
CommandBus
 ↓
PostgreSQL
 ↓
Job Queue
 ↓
Worker
 ↓
Job Handler
 ↓
Outbox
 ↓
Realtime
 ↓
Frontend/debug client
```

và:

```text
Authentication      PASS
Authorization       PASS

PostgreSQL          PASS

Retry               PASS
Lease               PASS
Fencing             PASS
Timeout             PASS
Cancellation        PASS
Restart recovery    PASS

Outbox              PASS
Realtime replay     PASS

Tracing             PASS

Architecture gates  PASS
```

Nếu chưa đạt, **không migrate Studio/Agent/Video**.

---

# 16. Giai đoạn B — bắt đầu chuyển functionality

Sau foundation mới chuyển code.

Thứ tự tôi khuyến nghị:

```text
Model Gateway
      ↓
Automation / Tools
      ↓
Agent Runtime
      ↓
Memory / Context
      ↓
Workspace
      ↓
Studio
      ↓
Production
      ↓
Live Record
      ↓
Quality / Eval
      ↓
Frontend
      ↓
Desktop
```

---

# 17. PHASE 11 — Model Gateway

Nguồn cũ:

```text
providers/*
+
intelligence/model_router/*
```

Target:

```text
modules/model_gateway/
```

### REWRITE

Các phần:

```text
registry
routing rules
endpoint selector
route lock
fallback
retry
circuit breaker
quota
health
receipt
```

### EXTRACT_LOGIC

Provider protocol behavior:

```text
OpenAI compatible
OpenRouter
Anthropic
Google
Mistral
NVIDIA
Ollama
```

Không để hai routing authority như kiến trúc cũ.

Target:

```text
ModelGateway = single authority
```

---

# 18. PHASE 12 — Automation / Tool Runtime

Nguồn:

```text
tools/*
execution/*
```

Target:

```text
modules/automation/
```

Viết lại quanh:

```text
ToolDefinition
ToolRegistry
ToolPolicy
ToolExecutor
ExecutionRuntime
```

Runtime adapters:

```text
in_process
subprocess
browser
MCP
desktop
container
remote
```

Đặc biệt:

```text
shell
filesystem write
browser side effect
```

bắt buộc đi qua Policy Engine.

---

# 19. PHASE 13 — Agent Runtime

Nguồn:

```text
orchestration/*
workflows/*
agent_loop/*
long_running/*
delegation/*
```

Target:

```text
modules/agent_runtime/
```

Đây sẽ là một trong những phần lớn nhất cần **REWRITE**.

```text
agent_runtime/
├── sessions/
├── runs/
├── planning/
├── tasks/
├── workflows/
├── scheduler/
├── checkpoints/
├── retry/
├── recovery/
├── approvals/
└── delegation/
```

Giữ semantics của:

```text
Task lifecycle
Workflow DAG
Retry
Checkpoint
Cancellation
Recovery
Budget
```

nhưng bỏ duplicated dispatcher authority.

Job execution thuộc:

```text
platform/job runtime
```

Agent Runtime chỉ **submit jobs**.

---

# 20. PHASE 14 — Context + Memory

Nguồn:

```text
context/*
memory/*
core memory contracts
```

Target:

```text
modules/memory/
modules/agent_runtime/context/
```

Phân biệt rõ:

```text
Context
= material assembled for current model call

Memory
= durable knowledge

State
= current execution state
```

Không trộn ba khái niệm.

---

# 21. PHASE 15 — Studio

Nguồn hiện tại phân tán:

```text
core/domain/story
intelligence/story
API studio
storage studio
orchestration studio
```

Target duy nhất:

```text
modules/studio/
```

Cấu trúc:

```text
studio/
├── public/
├── domain/
│   ├── projects/
│   ├── series/
│   ├── episodes/
│   ├── story/
│   ├── characters/
│   ├── world/
│   └── storyboard/
├── application/
├── infrastructure/
├── api/
└── jobs/
```

Một capability được đặt gần nhau thay vì chia thành 5 package technical.

---

# 22. PHASE 16 — Production

Nguồn:

```text
core/domain/video_production
intelligence/video
tools/production_engines
tools/media
tools/code_video
storage/video_production
workflows/video_production
```

Target:

```text
modules/production/
```

```text
production/
├── video/
├── assets/
├── audio/
├── code_video/
├── rendering/
├── postproduction/
└── jobs/
```

Đây là ví dụ rõ nhất cho lý do không nên copy cấu trúc cũ: một bounded context hiện bị chia qua rất nhiều package.

---

# 23. PHASE 17 — Live Record

Target riêng:

```text
modules/live_record/
```

Backend:

```text
plans
sessions
takes
cues
director
preparation
```

Native:

```text
apps/desktop/native/recording/
```

Recording engine production đã làm rất nhiều native work; ở phần này tôi sẽ **ADAPT + harden**, không rewrite mù quáng những đoạn Windows Graphics Capture/NVENC đã được kiểm chứng.

Điều cần rewrite là:

```text
boundary
IPC contract
state model
error model
lifecycle
```

---

# 24. PHASE 18 — Quality

Gom:

```text
evals/*
verification/*
```

thành:

```text
modules/quality/
├── evals/
├── regression/
├── verification/
├── quality_gates/
└── reports/
```

Không để verification nằm rời khỏi evaluation strategy.

---

# 25. Giai đoạn C — Frontend mới

Frontend cũ có 34 route, 23 feature và cả custom QueryClient lẫn TanStack Query.  

Không copy `frontend/app`.

Xây shell mới trước:

```text
frontend/app/src/
├── app/
│   ├── bootstrap/
│   ├── providers/
│   ├── router/
│   └── shell/
│
├── modules/
│
└── shared/
```

Foundation state:

```text
TanStack Query
    = server state

Zustand
    = UI state

Realtime
    = synchronization
```

Không viết custom QueryClient.

---

# 26. Frontend modules

Migration:

```text
OLD                         NEW

projects          → studio/projects
episodes          → studio/episodes
characters        → studio/characters
world             → studio/world
storyboard        → studio/storyboard
reviews           → studio/reviews

agents            → agent-system/agents
agent-workspace   → agent-system/workspace
workflows         → agent-system/workflows
memory            → agent-system/memory

providers         → model-gateway/providers
models            → model-gateway/models
routing           → model-gateway/routing

monitoring        → operations/monitoring
logs              → operations/logs
settings          → operations/settings

live-record       → live-record
production        → production
```

---

# 27. API SDK

Không chuyển `api-contracts` viết tay sang V2.

Dùng:

```text
Pydantic
 ↓
OpenAPI
 ↓
codegen
 ↓
@windagent/api-sdk
```

Frontend chỉ viết:

```text
UI model
ViewModel
form schema
```

Transport contract phải do backend sinh.

---

# 28. Những thứ có thể chuyển gần như nguyên trạng

Mặc dù ưu tiên rewrite, vẫn có vài thứ không cần lãng phí công sức viết lại.

### Có thể giữ

```text
design tokens
icons
static assets
fixtures
golden datasets
SQL test data
prompt fixtures
test vectors
```

### Có thể extract algorithm

```text
retry classification
fencing semantics
route scoring algorithm
token budgeting
specific evaluation algorithms
FFmpeg command construction
recording/native algorithms
```

Nhưng phải đặt chúng sau contract mới.

---

# 29. Mapping tổng thể old → V2

| Cũ                          | V2                                             | Strategy                        |
| --------------------------- | ---------------------------------------------- | ------------------------------- |
| `core/*`                    | `kernel + modules/*/domain`                    | **REWRITE/SPLIT**               |
| `storage/*`                 | `platform/persistence + module infrastructure` | **REWRITE**                     |
| `providers/*`               | `model_gateway`                                | **REWRITE**                     |
| `intelligence/model_router` | `model_gateway`                                | **MERGE + REWRITE**             |
| `orchestration/*`           | `agent_runtime + platform/jobs`                | **REWRITE**                     |
| `worker/pipeline`           | `platform/jobs + apps/worker`                  | **REWRITE, preserve semantics** |
| `tools/*`                   | `automation + production`                      | **SPLIT/REWRITE**               |
| `execution/*`               | `automation/runtime`                           | **REWRITE**                     |
| `intelligence/story`        | `studio`                                       | **REWRITE**                     |
| `intelligence/video`        | `production`                                   | **REWRITE**                     |
| `workflows/*`               | relevant module                                | **REWRITE**                     |
| `context/*`                 | `agent_runtime/context`                        | **REWRITE**                     |
| `memory/*`                  | `memory`                                       | **REWRITE**                     |
| `observability/*`           | `platform/observability`                       | **REWRITE**                     |
| `evals + verification`      | `quality`                                      | **MERGE**                       |
| `frontend/features`         | `frontend/modules`                             | **REWRITE**                     |
| `frontend/api-contracts`    | generated SDK                                  | **DELETE**                      |
| custom QueryClient          | TanStack Query                                 | **DELETE**                      |
| static UI tokens/assets     | UI package                                     | **KEEP_ASSET**                  |
| native recording backend    | desktop capability adapters                    | **ADAPT/HARDEN**                |

---

# 30. Parity test strategy

Đây là cách tránh rewrite rồi làm mất behavior.

Ví dụ routing:

```text
same input
   │
   ├── OLD ROUTER → result A
   │
   └── V2 ROUTER  → result B
```

Test:

```text
A == B
```

hoặc nếu cố ý thay đổi:

```text
V2 expected behavior
documented in ADR
```

Parity test dành cho:

```text
routing
scheduler
retry
workflow state transitions
queue ordering
provider normalization
context budgeting
memory selection
story transformations
production IR
```

---

# 31. Không migrate database theo kiểu copy ORM

ORM V2 phải viết mới.

Quy trình:

```text
old ORM
    ↓
understand domain/data
    ↓
design new aggregate
    ↓
design V2 schema
    ↓
new ORM
    ↓
migration importer
```

Không:

```text
copy v3_models.py
rename package
```

---

# 32. Commit strategy

Mỗi phase phải là commit/series độc lập.

Ví dụ:

```text
v2/foundation-01-repository
v2/foundation-02-kernel
v2/foundation-03-platform-contracts
v2/foundation-04-module-runtime
v2/foundation-05-persistence
v2/foundation-06-events
v2/foundation-07-job-runtime
v2/foundation-08-api
v2/foundation-09-security
v2/foundation-10-observability
```

Sau đó:

```text
v2/module-model-gateway
v2/module-automation
v2/module-agent-runtime
...
```

Không commit 5.000 file trong một lần.

---

# 33. Cutover strategy

Không chuyển tất cả rồi mới chạy.

Mỗi bounded context có:

```text
DESIGN
 ↓
IMPLEMENT
 ↓
UNIT
 ↓
PARITY
 ↓
POSTGRES INTEGRATION
 ↓
E2E
 ↓
CUTOVER
 ↓
OLD MODULE → READ ONLY
 ↓
OLD MODULE → DELETE
```

Điều này cho phép biết chính xác module nào đã thực sự hoàn thành.

---

# 34. Migration status board

Tạo:

```text
docs/migration/MIGRATION_STATUS.md
```

Theo format:

| Module        | Design | Rewrite | Unit | Parity | Integration | Cutover |
| ------------- | -----: | ------: | ---: | -----: | ----------: | ------: |
| Kernel        |      ✅ |       ✅ |    ✅ |    N/A |           ✅ |       ✅ |
| Jobs          |      ✅ |      🔄 |      |        |             |         |
| Model Gateway |        |         |      |        |             |         |
| Agent Runtime |        |         |      |        |             |         |
| Studio        |        |         |      |        |             |         |
| Production    |        |         |      |        |             |         |

Không dựa vào cảm giác “đã chuyển gần hết”.

---

# 35. Quy tắc chống việc V2 lại thành WindAgent cũ

CI nên cấm trực tiếp:

```text
Wind_agent_v2 imports ../core
Wind_agent_v2 imports ../storage
Wind_agent_v2 imports ../providers
Wind_agent_v2 imports ../orchestration
```

Ngoài ra:

```text
domain → SQLAlchemy                 DENY
domain → FastAPI                    DENY
module → provider adapter directly  DENY
module A → module B/infrastructure  DENY

API → repository                    DENY
API → ORM                           DENY

tool → bypass PolicyEngine          DENY

production SQLite                   DENY
```

---

# 36. Mốc triển khai tôi sẽ dùng

Toàn bộ migration chia thành 4 milestone lớn:

```text
MILESTONE 1
V2 FOUNDATION
────────────────
Kernel
Platform
Module runtime
PostgreSQL
Events
Jobs
Worker
API
Security
Observability
```

↓

```text
MILESTONE 2
AGENT PLATFORM
────────────────
Model Gateway
Automation
Agent Runtime
Context
Memory
```

↓

```text
MILESTONE 3
WINDAGENT PRODUCT
────────────────
Workspace
Studio
Production
Live Record
Quality
```

↓

```text
MILESTONE 4
USER PLATFORM
────────────────
Frontend
Desktop
Data migration
E2E
Production deployment
Old-system retirement
```

---

# 37. Gate quan trọng nhất

Tôi **không chuyển một file business nào vào `Wind_agent_v2` trước khi Milestone 1 PASS**.

Đây là điểm tôi muốn khóa cứng.

Nếu bắt đầu bằng:

```text
copy core
copy storage
copy frontend
```

thì sau vài tuần `Wind_agent_v2` sẽ trở thành:

> WindAgent cũ với tên folder mới.

Cách đúng là:

```text
        BUILD NEW FOUNDATION

Kernel
Platform
Module Runtime
Command/Query
Jobs
Events
Persistence
Security
Observability
API
Worker
Realtime
        │
        │ FOUNDATION FROZEN
        ▼
      MIGRATE

Model Gateway
Automation
Agent Runtime
Memory
Studio
Production
Live Record
Frontend
Desktop
```

Với cấu trúc hiện tại — đặc biệt là worker durable queue/lease/fencing đáng giữ về semantics, cùng với sự phân mảnh giữa `core`, `orchestration`, `intelligence`, `tools`, `providers` — **rewrite theo bounded context trong `Wind_agent_v2` là hướng tốt hơn rất nhiều so với filesystem refactor tại chỗ**.  

Bước triển khai đầu tiên nên là **Phase 0 → Phase 7**, tức dựng toàn bộ skeleton, architecture gates, kernel, platform contracts, PostgreSQL, event/outbox và worker/job runtime trong `Wind_agent_v2` trước; chưa chuyển `Studio`, `Agent`, `Production` hay frontend vào đó.
