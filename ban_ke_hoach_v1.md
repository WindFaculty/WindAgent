Dưới đây là kế hoạch triển khai chi tiết **Phase 0 → Phase 5** cho đợt **Frontend Architecture V2 + Unified API V3**, dựa trực tiếp trên roadmap bạn gửi và đối chiếu repository `WindFaculty/WindAgent` tại snapshot `ac2c19c59ca3c16c86e81d761c0a70b911bb294e`. 

Tôi giữ nguyên nguyên tắc quan trọng của roadmap: **không big-bang rewrite, không xóa V2/mock sớm, không thay đổi business/domain logic nếu không cần thiết**.

Hiện trạng GitHub xác nhận các vấn đề nền tảng cần xử lý trong 0–5:

* `apps/desktop/src/App.tsx` vẫn tự quản lý `activeTab`, `visitedTabs`, hash routing, health polling, metrics và Tauri detection.
* Web hiện chỉ import nguyên Desktop App và Desktop CSS.
* `apps/desktop/src/api/client.ts` vẫn là handwritten client, direct `fetch()`, nhiều `/api/v2/*` và nhiều `v2Unavailable()`.
* Backend đang đồng thời đăng ký nhiều V2 router và `/api/v3/studio`; middleware lại gắn `/api/v3/studio` làm successor chung cho toàn `/api/v2`, không đúng semantic.
* `HttpStudioApiClient` hiện là implementation tốt để kế thừa: timeout, typed error, GET retry có giới hạn, mutation bắt buộc idempotency key.
* Desktop hiện có Redux + Zustand nhưng chưa có router/query architecture mục tiêu.
* `styles.css` đã khoảng 120 KB và thực ra đã có khá nhiều design token + primitive; Phase 5 vì thế nên **extract/converge**, không viết lại visual từ số 0.

---

# Tổng quan Phase 0–5

| Phase | Mục tiêu                                      | Runtime behavior           |
| ----- | --------------------------------------------- | -------------------------- |
| **0** | Freeze + inventory toàn bộ frontend/API       | Không đổi                  |
| **1** | Chốt vocabulary/domain semantics              | Không đổi                  |
| **2** | Xây nền Unified API V3                        | Additive                   |
| **3** | OpenAPI → generated client + realtime package | Additive                   |
| **4** | Shared Frontend App + Router + Providers      | Cutover shell có kiểm soát |
| **5** | Design System extraction/convergence          | Không redesign             |

Mốc quan trọng:

```text
P0 ──> P1 ──> P2 ──> P3 ──> P4 ──> P5
       │       │       │       │
       │       │       │       └── Shared Web/Desktop shell
       │       │       └── Typed/generated transport
       │       └── Canonical V3 contracts
       └── Domain vocabulary authority
```

**Không bắt đầu migrate Dashboard, Projects, Studio... trong Phase 0–5.** Việc migrate feature thực sự bắt đầu từ Phase 6.

---

# Phase 0 — Freeze & Inventory

## Mục tiêu

Tạo **baseline có thể chứng minh** trước khi thay đổi architecture.

Phase này tuyệt đối không được:

```text
xóa V2
xóa mock
xóa page cũ
rewrite page
đổi UI
đổi endpoint behavior
sửa business logic
```

Chỉ được thêm script audit, artifact, test baseline và tài liệu.

### Verdict đề xuất

```text
FEV3_P0_BASELINE_FROZEN
```

---

## P0.1 — Khóa baseline

Lưu:

```text
repository
branch
HEAD SHA
timestamp
Python version
Node version
npm/pnpm version
OS
architecture version
API version
frontend package versions
```

Tạo:

```text
artifacts/frontend_restructure/phase_00/baseline/
├── baseline_manifest.json
├── environment_manifest.json
├── git_manifest.json
└── baseline_verdict.json
```

`baseline_manifest.json` tối thiểu:

```json
{
  "baseline_sha": "...",
  "worktree_clean": true,
  "frontend_behavior_modified": false,
  "api_behavior_modified": false
}
```

---

# P0.2 — Frontend file inventory

Viết script audit toàn bộ:

```text
apps/desktop/
apps/web/
frontend/
```

Phân loại mỗi file:

```text
BOOTSTRAP
APP_SHELL
PAGE
FEATURE
COMPONENT
STATE
API_CLIENT
CONTRACT
PLATFORM
STYLE
TEST
MOCK
LEGACY
UNKNOWN
```

Output:

```text
frontend_file_inventory.json
```

Schema:

```json
{
  "path": "apps/desktop/src/pages/EpisodesPage.tsx",
  "category": "PAGE",
  "imports": [],
  "consumers": [],
  "runtime_reachable": true,
  "contains_mock_data": true,
  "contains_direct_fetch": false,
  "decision": "MIGRATE"
}
```

Không đánh `REMOVE` chỉ vì chưa tìm thấy import. Phase 0 chỉ inventory.

---

# P0.3 — Route/navigation inventory

Audit đồng thời:

```text
App.tsx
DESKTOP_NAVIGATION_GROUPS
window.location.hash
activeTab
lazy imports
sidebar item IDs
```

Tạo:

```text
route_inventory.json
navigation_inventory.json
route_navigation_mismatch.json
```

Cần phát hiện tự động các trường hợp:

```text
navigation exists + no route
route exists + no navigation
different IDs for same page
manual hash route
duplicate route authority
```

Ví dụ hiện tại `App.tsx` rõ ràng đang tự chuyển hash thành `activeTab`; chính logic này sẽ trở thành baseline cần loại bỏ ở Phase 4.

---

# P0.4 — API inventory

Không chỉ grep URL.

Phải lập matrix:

```text
Frontend consumer
        ↓
API client/function
        ↓
method + route
        ↓
FastAPI router
        ↓
application service
        ↓
mock / persistent / real runtime
```

Output:

```text
api_endpoint_inventory.json
api_consumer_matrix.json
```

Mỗi endpoint:

```json
{
  "method": "GET",
  "path": "/api/v2/providers",
  "api_generation": "V2",
  "frontend_consumers": [],
  "backend_router": "...",
  "runtime_status": "REAL|FIXTURE|STUB|UNKNOWN",
  "replacement": null,
  "decision": "KEEP|MIGRATE|MERGE|REWRITE|REMOVE"
}
```

Inventory riêng:

```text
/api/v2/
/api/v3/
/api/models/
direct fetch()
v2Unavailable()
```

`apps/desktop/src/api/client.ts` phải được xem như một nguồn legacy authority quan trọng vì hiện nó vừa có endpoint thật vừa có `v2Unavailable`.

---

# P0.5 — Mock inventory

Quét:

```text
DEFAULT_*
MOCK_*
Fake*
mock*
setTimeout(...)
Math.random()
hardcoded runtime arrays
static progress
fallback-to-mock
```

Output:

```text
mock_data_inventory.json
```

Phân biệt:

```text
TEST_FIXTURE       → hợp lệ
STORYBOOK_FIXTURE  → hợp lệ
DEV_FIXTURE        → xem xét
PRODUCTION_RUNTIME → phải migrate sau
```

Không xóa gì trong P0.

---

# P0.6 — State management inventory

Phát hiện:

```text
Redux Toolkit
React Redux
Zustand
StudioStore
Context Provider
useState
useReducer
server data stored locally
```

Output:

```text
state_management_inventory.json
```

Đặc biệt đánh dấu:

```text
SERVER_STATE
LOCAL_UI_STATE
WORKFLOW_STATE
URL_STATE
PLATFORM_STATE
REALTIME_STATE
```

Đây là cơ sở để sau này chuyển về:

```text
Server state → TanStack Query
UI state     → Zustand
URL state    → Router
Workflow     → backend
Realtime     → realtime client
```

Không migrate state trong Phase 0.

---

# P0.7 — CSS/design audit

Phải inventory stylesheet 120 KB hiện tại thay vì coi nó là dead CSS.

Tạo:

```text
css_token_inventory.json
css_selector_inventory.json
css_duplicate_report.json
design_system_baseline.md
```

Phân loại token hiện có:

```text
global tokens
Stitch tokens
Studio semantic tokens
status tokens
layout tokens
component primitives
feature/page selectors
```

Current CSS đã có `--studio-*`, `--status-*`, `.ui-button`, `.ui-badge`... nên Phase 5 phải tái sử dụng chúng.

---

# P0.8 — Baseline test matrix

Chạy toàn bộ test hiện có, nhưng **không tự sửa test fail ngoài scope**.

Thu thập:

```text
Python tests
architecture checks
API tests
Desktop unit
Desktop typecheck
Desktop build
Web unit
Web typecheck
Web build
Studio client tests
Production client tests
```

Output:

```text
test_matrix.json
build_matrix.json
baseline_failures.json
```

Nếu test đã fail trước Phase 0:

```text
PRE_EXISTING_FAILURE
```

Không được âm thầm fix rồi gọi Phase 0 PASS.

---

## Phase 0 artifacts cuối cùng

```text
artifacts/frontend_restructure/phase_00/
├── baseline/
│   ├── baseline_manifest.json
│   ├── environment_manifest.json
│   └── git_manifest.json
├── frontend_file_inventory.json
├── route_inventory.json
├── navigation_inventory.json
├── route_navigation_mismatch.json
├── api_endpoint_inventory.json
├── api_consumer_matrix.json
├── mock_data_inventory.json
├── direct_fetch_inventory.json
├── state_management_inventory.json
├── css_token_inventory.json
├── css_selector_inventory.json
├── package_inventory.json
├── test_matrix.json
├── build_matrix.json
├── risk_register.md
├── baseline_report.md
└── final_verdict.json
```

### Phase 0 PASS khi

```text
inventory coverage >= 100% production frontend source
route/navigation inventory complete
API consumer matrix complete
mock inventory complete
direct fetch inventory complete
baseline tests captured
baseline SHA frozen
worktree state recorded
runtime behavior changes = 0
```

---

# Phase 1 — Canonical Domain Vocabulary

## Mục tiêu

Đây là phase kiến trúc, không phải coding feature.

Không được dựng API V3 toàn hệ thống khi các từ như `Series`, `Project`, `Run`, `Revision`, `Agent` vẫn có nhiều nghĩa.

Verdict:

```text
FEV3_P1_DOMAIN_VOCABULARY_FROZEN
```

---

# P1.1 — Project vs Series

Đề xuất canonical:

```text
Project
├── Episodes
├── Characters
├── World
├── Assets
└── Production configuration
```

`Project` = aggregate/root người dùng nhìn thấy.

`Series` hiện tại:

```text
StudioSeries
series_id
/api/v3/studio/series
```

không xóa ngay.

Quyết định:

```text
Project = canonical terminology mới
Series  = compatibility concept trong migration window
```

Tạo ADR:

```text
docs/architecture/adr/
ADR-FE-001-project-vs-series.md
```

Nội dung phải mô tả:

```text
old concept
new concept
mapping
migration rule
database implications
API implications
frontend implications
removal phase
```

---

# P1.2 — AgentDefinition vs AgentInstance

Canonical:

```text
AgentDefinition
= cấu hình/template agent

AgentInstance
= một runtime execution instance cụ thể
```

Không dùng `Agent` mơ hồ trong V3 contract.

---

# P1.3 — File vs Artifact vs Asset

Khóa semantic:

```text
File
= filesystem/workspace resource

Artifact
= immutable output của pipeline

Asset
= production resource có thể được version/review/reuse
```

Ví dụ:

```text
screenplay JSON → Artifact
character model → Asset
user-uploaded .txt → File
```

---

# P1.4 — Task / Run / WorkflowRun

Đề xuất:

```text
Task
= unit of requested work

Run
= execution attempt

WorkflowDefinition
= reusable DAG/template

WorkflowRun
= execution instance của workflow
```

Không để một `run_id` vừa có nghĩa Studio generation vừa có nghĩa generic workflow nếu không namespace rõ.

---

# P1.5 — Revision vs Version

Đây là quyết định quan trọng cho Phase 2.

Khóa:

```text
Revision
= immutable content snapshot

version
= mutable optimistic concurrency counter
```

Ví dụ:

```json
{
  "revision_id": "rev_123",
  "version": 12
}
```

Mutation:

```json
{
  "expected_version": 12
}
```

Tôi đề xuất dùng **`version/expected_version` làm concurrency authority** thay vì triển khai đồng thời cả `ETag/If-Match`.

Lý do: Studio hiện đã có optimistic version trong contract, nên convergence rủi ro thấp hơn.

---

# P1.6 — Memory vs Database

Canonical:

```text
Memory
= contextual/agent memory

Database
= persistence/runtime administration
```

Nếu không có nhu cầu database administration trong UI:

```text
sidebar "Database" → "Memory"
```

Không gọi memory records là database nữa.

---

## Phase 1 output

```text
docs/architecture/frontend_v3/
├── canonical_vocabulary.md
├── aggregate_map.md
├── resource_identity_rules.md
└── migration_glossary.md

docs/architecture/adr/
├── ADR-FE-001-project-vs-series.md
├── ADR-FE-002-agent-definition-instance.md
├── ADR-FE-003-file-artifact-asset.md
├── ADR-FE-004-task-run-workflow-run.md
├── ADR-FE-005-revision-version.md
└── ADR-FE-006-memory-database.md
```

Thêm machine-readable:

```text
artifacts/frontend_restructure/phase_01/
├── vocabulary_manifest.json
├── legacy_to_canonical_map.json
├── unresolved_terms.json
└── final_verdict.json
```

### Gate

```text
unresolved critical vocabulary = 0
duplicate canonical definition = 0
V3 naming convention frozen
concurrency model frozen
identity rules frozen
```

---

# Phase 2 — Unified API V3 Foundation

## Mục tiêu

**Không migrate tất cả V2 endpoint.**

Xây infrastructure để các phase sau có thể thêm:

```text
/api/v3/projects
/api/v3/assets
/api/v3/agents
...
```

mà không tiếp tục tạo contract tùy tiện.

Verdict:

```text
FEV3_P2_API_FOUNDATION_VERIFIED
```

Backend hiện có additive `/api/v3/studio` bên cạnh hàng loạt V2 router nên có thể tiếp tục dùng strangler migration.

---

# P2.1 — V3 root infrastructure

Tổ chức:

```text
apps/api/windagent_api/routers/v3/
├── __init__.py
├── router.py
├── common/
└── studio/             # existing
```

`router.py` trở thành aggregator V3 duy nhất:

```python
v3_router = APIRouter(prefix="/api/v3")
```

Sau đó:

```text
main.py
  ↓
include_router(v3_router)
```

Không để main import hàng chục V3 domain router về sau.

---

# P2.2 — ApiProblem

Chuẩn một error contract.

```json
{
  "type": "https://windagent.dev/problems/revision-conflict",
  "title": "Revision conflict",
  "status": 409,
  "detail": "...",
  "code": "REVISION_CONFLICT",
  "correlation_id": "...",
  "retryable": false,
  "details": {}
}
```

Tất cả V3 exception handler dùng cùng contract.

Không sửa response contract V2 trong phase này.

---

# P2.3 — Resource base

Canonical base metadata:

```json
{
  "id": "...",
  "created_at": "...",
  "updated_at": "...",
  "version": 12
}
```

Không bắt tất cả domain expose cùng exact Pydantic class nếu semantic không phù hợp, nhưng field naming phải thống nhất.

---

# P2.4 — Pagination

Chuẩn cursor pagination:

```json
{
  "items": [],
  "page_info": {
    "next_cursor": null,
    "has_more": false
  }
}
```

Cấm tạo mới trong V3:

```text
page
page_size
offset
start
continuation
```

trừ endpoint có lý do cụ thể được ADR ghi nhận.

---

# P2.5 — Correlation ID

Middleware:

```text
request
 ↓
X-Correlation-ID supplied?
 ├─ yes → preserve
 └─ no  → generate
```

Echo:

```text
X-Correlation-ID
```

và error body:

```text
correlation_id
```

Trace phải đi xuyên:

```text
frontend → API → task/run → events → logs
```

---

# P2.6 — Idempotency

Mutation quan trọng:

```text
POST
PATCH
DELETE
```

hỗ trợ:

```http
Idempotency-Key: UUID
```

Server lưu:

```text
key
actor
route
request fingerprint
result fingerprint
created_at
expires_at
```

Rules:

```text
same key + same request  → replay response
same key + different body → 409 IDEMPOTENCY_CONFLICT
```

Studio client đang yêu cầu idempotency key từ caller; nguyên tắc này nên được giữ lại và đưa thành canonical contract.

---

# P2.7 — Optimistic concurrency

Canonical request:

```json
{
  "expected_version": 12
}
```

Nếu current:

```text
13
```

return:

```text
409 VERSION_CONFLICT
```

Không silently overwrite.

---

# P2.8 — Command receipt

Đối với async command:

```json
{
  "command_id": "...",
  "status": "ACCEPTED",
  "resource_id": "...",
  "correlation_id": "...",
  "submitted_at": "..."
}
```

HTTP:

```text
202 Accepted
```

Không trả fake final result nếu job chưa chạy.

---

# P2.9 — EventEnvelope

Canonical:

```json
{
  "event_id": "...",
  "aggregate_type": "episode",
  "aggregate_id": "...",
  "sequence": 128,
  "event_type": "screenplay.generated",
  "occurred_at": "...",
  "correlation_id": "...",
  "payload": {}
}
```

Invariants:

```text
sequence monotonic per stream
event_id globally unique
event immutable
correlation_id propagated
payload typed by event_type
```

---

# P2.10 — Sửa deprecation semantics

Hiện backend gắn tất cả `/api/v2/*` với successor `/api/v3/studio`.

Sửa thành:

```text
không claim một successor chung
```

Chỉ gắn successor khi domain thực sự đã có V3 replacement.

Ví dụ:

```text
/api/v2/assets
→ successor sau khi /api/v3/assets tồn tại
```

Trong thời gian chưa có replacement:

```text
V2 vẫn reachable
không redirect
không 410
không nói sai successor
```

---

# P2.11 — OpenAPI quality gate

Mọi V3 operation:

```text
operation_id unique
request model explicit
response model explicit
error contract documented
tags canonical
description meaningful
```

CI kiểm:

```text
duplicate operation_id = FAIL
missing response schema = FAIL
OpenAPI generation = FAIL → gate fail
```

---

## Phase 2 tests

Tối thiểu:

```text
ApiProblem tests
correlation ID tests
idempotency replay tests
idempotency conflict tests
expected_version conflict tests
pagination schema tests
EventEnvelope serialization tests
OpenAPI operation ID uniqueness
V2 regression tests
Studio V3 regression tests
```

Quan trọng:

```text
V2 functional regression = 0
Studio V3 regression = 0
```

---

# Phase 3 — Generated API Client

## Mục tiêu

Biến:

```text
Pydantic
   ↓
FastAPI OpenAPI
   ↓
generated TS contracts/client
   ↓
frontend
```

thành **contract authority duy nhất**.

Verdict:

```text
FEV3_P3_GENERATED_CLIENT_VERIFIED
```

---

# P3.1 — Tạo package mới

```text
frontend/packages/
├── api-contracts/
├── api-client/
└── realtime/
```

Không tạo thêm package theo từng page.

Existing `studio-client`, `production-client` vẫn giữ trong migration window. Repository hiện đã có nhiều package riêng cho Studio và Production, do đó P3 phải hướng tới convergence thay vì tiếp tục nhân package.

---

# P3.2 — OpenAPI generation pipeline

Pipeline:

```text
FastAPI app
  ↓
openapi.json
  ↓
validate schema
  ↓
generate TypeScript
  ↓
format
  ↓
typecheck
  ↓
check git diff
```

Tạo script:

```text
scripts/frontend_api/
├── export_openapi.py
├── validate_openapi.py
└── generate_client.*
```

Output OpenAPI:

```text
artifacts/frontend_restructure/openapi/openapi-v3.json
```

---

# P3.3 — api-contracts

Package chứa generated types.

Không đặt business logic.

Ví dụ:

```text
@windagent/api-contracts
```

Public exports:

```ts
ApiProblem
PageInfo
ProjectResource
EpisodeResource
EventEnvelope
...
```

Không tiếp tục tạo:

```text
apps/desktop/src/api/types.ts
studio-contracts duplicate type
production-contracts duplicate type
```

cho V3 mới.

Legacy packages chưa xóa.

---

# P3.4 — api-client

Xây transport chung dựa trên những nguyên tắc đã hoạt động tốt trong `HttpStudioApiClient`.

Transport chịu trách nhiệm:

```text
base URL
timeout
correlation ID
typed ApiProblem
network errors
GET retry
idempotency key
JSON serialization
204 handling
abort signal
```

Nguyên tắc retry:

```text
GET:
  network failure → có thể retry

Mutation:
  không tự retry tùy tiện

POST/PATCH/DELETE:
  retry chỉ khi caller dùng cùng Idempotency-Key
```

---

# P3.5 — API façade

Frontend feature không gọi URL.

Target:

```ts
api.projects.list()
api.projects.get(id)

api.episodes.create(...)
api.assets.get(id)

api.agentInstances.stop(id)
```

Feature code không được biết:

```text
/api/v3/...
```

URL chỉ nằm trong generated/transport layer.

---

# P3.6 — Realtime package

```text
@windagent/realtime
```

Responsibilities:

```text
connect
disconnect
heartbeat
reconnect
exponential backoff
resume from sequence
event dedup
gap detection
snapshot recovery
subscription routing
```

State:

```text
DISCONNECTED
CONNECTING
CONNECTED
DEGRADED
RESYNCING
```

API:

```ts
subscribe({
  aggregateType,
  aggregateId,
  afterSequence
})
```

---

# P3.7 — Architecture rule: cấm direct fetch

Sau Phase 3:

```text
feature/page production code
        ↓
direct fetch()
        =
FORBIDDEN
```

Cho phép:

```text
api-client transport
service worker/platform adapter nếu cần
test fixture
```

Thêm checker vào CI.

Không yêu cầu direct fetch production = 0 ngay lúc Phase 3, vì legacy page chưa migrate.

Thay vào đó:

```text
new direct fetch introduced after baseline = 0
```

Sau Phase 15 mới yêu cầu toàn repo = 0.

Đây là khác biệt rất quan trọng để không biến migration thành big-bang.

---

# Phase 3 gate

```text
OpenAPI export PASS
OpenAPI validation PASS
generated TS PASS
generated client typecheck PASS
transport tests PASS
realtime tests PASS
new direct-fetch violations = 0
V2 regression PASS
Studio regression PASS
```

Artifacts:

```text
phase_03/
├── openapi_manifest.json
├── generation_manifest.json
├── operation_id_report.json
├── client_contract_report.json
├── direct_fetch_delta.json
└── final_verdict.json
```

---

# Phase 4 — Frontend Foundation

Đây là phase thay đổi frontend architecture lớn nhất trong 0–5.

## Mục tiêu

Từ:

```text
apps/web
   ↓
apps/desktop/App.tsx
```

sang:

```text
                  apps/web
                     ↓
frontend/app ─────────────
                     ↑
                apps/desktop
```

Hiện Web đúng nghĩa chỉ render Desktop App.

Verdict:

```text
FEV3_P4_SHARED_FRONTEND_FOUNDATION_VERIFIED
```

---

# P4.1 — Tạo shared app

```text
frontend/app/
├── package.json
├── tsconfig.json
└── src/
    ├── app/
    │   ├── App.tsx
    │   ├── router.tsx
    │   ├── routeManifest.ts
    │   ├── providers.tsx
    │   ├── bootstrap.ts
    │   └── errors/
    │
    ├── features/
    └── shared/
```

---

# P4.2 — Platform bootstrap

Desktop:

```text
apps/desktop/src/main.tsx
    ↓
bootstrap shared frontend
    ↓
TauriPlatformAdapter
```

Web:

```text
apps/web/src/main.tsx
    ↓
bootstrap shared frontend
    ↓
WebPlatformAdapter
```

Không còn:

```ts
import { App } from "@desktop/App";
```

---

# P4.3 — PlatformAdapter

Interface:

```ts
interface PlatformAdapter {
  kind: 'web' | 'tauri';

  getSystemMetrics(): Promise<...>;

  openExternal(url: string): Promise<void>;

  selectFile?(...): Promise<...>;

  getSecureCredential?(...): Promise<...>;
}
```

Implement:

```text
WebPlatformAdapter
TauriPlatformAdapter
```

Feature không được gọi trực tiếp:

```ts
window.__TAURI__
invoke(...)
```

---

# P4.4 — Router chuẩn

Giữ **HashRouter** nếu phù hợp với Tauri, nhưng routing phải do router library quản lý.

Canonical tree ban đầu:

```text
/dashboard

/studio
/studio/projects
/studio/projects/:projectId

/studio/episodes
/studio/episodes/:episodeId

/studio/characters
/studio/world

/assets

/models
/models/providers
/models/routing

/agents
/workspace/:conversationId
/workflows

/browser
/files

/monitoring
/logs
/database

/settings
```

Giai đoạn này route có thể vẫn render legacy page.

Mục đích là **chuyển authority**, không phải migrate feature.

---

# P4.5 — Route manifest

Một nguồn sự thật:

```ts
routeManifest
```

Mỗi record:

```ts
{
  id,
  path,
  label,
  icon,
  group,
  component,
  breadcrumb,
  capabilities,
  navigationVisible
}
```

Từ manifest sinh:

```text
Router
Sidebar
Breadcrumb
Keyboard navigation
Page title
```

Cấm:

```text
Sidebar có route list riêng
App có route list riêng
hash parser có mapping riêng
```

---

# P4.6 — Xóa TabKeeper architecture

`App.tsx` hiện đang dùng:

```text
activeTab
visitedTabs
TabKeeper
window.location.hash
hashchange
```

Phase 4 loại architecture này khỏi shell.

Router quyết định lifecycle component.

Nếu một page cần giữ state khi navigation:

```text
URL state
Query cache
small Zustand UI state
```

không dùng hidden mounted tab làm default solution.

---

# P4.7 — Provider hierarchy

`providers.tsx`:

```text
ErrorBoundary
   ↓
PlatformProvider
   ↓
ApiProvider
   ↓
QueryClientProvider
   ↓
RealtimeProvider
   ↓
UIStateProvider
   ↓
Router
```

Không tạo StudioStore trong page.

---

# P4.8 — TanStack Query foundation

Desktop package hiện đang có Redux + Zustand nhưng chưa có query architecture mục tiêu.

Phase 4 bổ sung Query infrastructure, chưa cần migrate mọi page.

Canonical query keys:

```ts
['projects']
['project', projectId]

['episodes', projectId]
['episode', episodeId]

['assets', filters]
```

Mutation:

```text
invalidate exact domain query
update cache from realtime event
```

---

# P4.9 — Zustand scope

Zustand chỉ cho UI state như:

```text
sidebar collapsed
panel size
selected inspector tab
command palette
local view preference
```

Không lưu canonical:

```text
projects
episodes
assets
workflows
```

nếu chúng thuộc backend server state.

---

# P4.10 — Error Boundary

Tách:

```text
GlobalErrorBoundary
RouteErrorBoundary
FeatureErrorState
```

Phân biệt:

```text
network unavailable
401/403
404
409 conflict
422 validation
500
unsupported capability
```

Không `catch {}` rồi fallback mock.

---

# P4.11 — Legacy route bridge

Đây là yếu tố giúp Phase 4 an toàn.

Ví dụ:

```text
/dashboard
    ↓
new Router
    ↓
legacy Dashboard component
```

Phase 4 **không yêu cầu Dashboard đã dùng V3 API**.

Tương tự:

```text
/agents → existing Agents
/browser → existing Browser
```

Sau Phase 6 trở đi sẽ thay từng implementation.

---

## Phase 4 gate

Bắt buộc:

```text
Web imports Desktop App                = 0
manual hash parser in shared shell     = 0
activeTab route authority              = 0
TabKeeper route authority              = 0
route manifest authorities             = 1

Desktop starts                         PASS
Web starts                             PASS

Desktop build                          PASS
Web build                              PASS

all baseline routes reachable          PASS
back/forward navigation                PASS
deep-link/hash refresh                 PASS
route 404                              PASS
```

**Feature behavior parity phải giữ nguyên.**

---

# Phase 5 — Design System

## Mục tiêu

Không redesign lại WindAgent.

Mục tiêu:

```text
120 KB global stylesheet
        ↓
tokens + primitives + layout + feature styles
```

và giữ visual hiện tại.

Verdict:

```text
FEV3_P5_DESIGN_SYSTEM_VERIFIED
```

---

# P5.1 — Tạo shared UI package

Đề xuất:

```text
frontend/packages/ui/
├── package.json
└── src/
    ├── tokens/
    ├── theme/
    ├── components/
    ├── layout/
    ├── feedback/
    └── index.ts
```

---

# P5.2 — Extract token

Từ CSS hiện tại giữ lại semantic trước.

```text
tokens/
├── colors.css
├── typography.css
├── spacing.css
├── radius.css
├── shadows.css
├── z-index.css
├── motion.css
└── layout.css
```

Không đổi giá trị màu chỉ vì đang refactor.

Các token hiện có như:

```text
--studio-bg
--studio-surface-*
--studio-border
--studio-text-*
--status-running
--status-success
```

nên trở thành foundation chứ không bị thay mất.

---

# P5.3 — Theme

```text
theme/
├── dark.css
└── index.css
```

Hiện tại chỉ cần bảo toàn Kinetic Obsidian/dark design.

Không cần ép light mode nếu application chưa dùng.

---

# P5.4 — UI primitives

Ưu tiên component có usage lớn:

```text
Button
IconButton
Input
Textarea
Select
Checkbox
Switch
Badge
StatusBadge
Card
Panel
Tabs
Table
Modal
Dialog
Tooltip
Toast
Skeleton
EmptyState
ErrorState
Spinner
```

Không tạo component wrapper chỉ để đổi tên HTML.

---

# P5.5 — Layout primitives

```text
AppShell
PageHeader
PageBody
SplitPane
Sidebar
TopBar
Toolbar
InspectorPanel
Stack
Grid
```

`studio-shell` hiện có thể được:

```text
giữ
refactor
merge từng phần vào shared UI
```

Không xóa package ngay ở P5.

---

# P5.6 — Compatibility CSS

Đây là phần rất quan trọng.

Không rewrite toàn bộ selectors trong một commit.

Tạm giữ alias:

```css
.ui-button { ... }
```

trỏ tới semantic mới hoặc giữ style tương thích.

Cho phép legacy page tiếp tục render giống trước khi migrate.

---

# P5.7 — Accessibility baseline

Mỗi primitive mới:

```text
keyboard usable
focus-visible
disabled semantics
aria-label khi icon-only
dialog focus trap
Escape handling
contrast
44px interactive target khi cần
```

---

# P5.8 — Visual regression

Lưu screenshot canonical:

```text
Dashboard
Studio
Projects
Agent Workspace
Models
Settings
```

Trước / sau extraction.

Mục tiêu P5:

```text
visual change không chủ ý = 0
```

Không dùng screenshot để ép pixel-perfect những chỗ dynamic, nhưng layout chính phải giữ.

---

# P5.9 — Loại duplication

Sau extraction kiểm tra:

```text
duplicate button definitions
duplicate modal definitions
duplicate status colors
duplicate typography
duplicate spacing constants
```

Không xóa selector mà còn runtime consumer.

---

# Phase 5 gate

```text
shared tokens package             PASS
shared primitives                 PASS
desktop consumes shared UI        PASS
web consumes same UI              PASS

visual regression                PASS
component tests                  PASS
keyboard tests                   PASS
typecheck                        PASS

runtime feature behavior change   = 0
unintentional visual change       = 0
```

---

# Cấu trúc dự kiến sau Phase 5

```text
apps/
├── desktop/
│   └── src/
│       └── main.tsx
│
└── web/
    └── src/
        └── main.tsx

frontend/
├── app/
│   └── src/
│       ├── app/
│       │   ├── App.tsx
│       │   ├── router.tsx
│       │   ├── routeManifest.ts
│       │   ├── providers.tsx
│       │   └── bootstrap.ts
│       │
│       ├── features/
│       └── shared/
│
└── packages/
    ├── ui/
    ├── api-contracts/
    ├── api-client/
    ├── realtime/
    │
    ├── studio-client/        # legacy/migration
    ├── studio-contracts/     # legacy/migration
    ├── studio-state/         # legacy/migration
    ├── production-client/    # legacy/migration
    └── ...

apps/api/windagent_api/
└── routers/
    ├── v2_*                  # vẫn tồn tại
    └── v3/
        ├── router.py
        ├── common/
        └── studio/
```

Điểm quan trọng: **các package legacy vẫn còn sau Phase 5**. Repository hiện đã có nhiều package Studio/Production riêng biệt; việc xóa chúng phải đợi các vertical slice migrate xong.

---

# Những việc tuyệt đối chưa làm trong Phase 0–5

Để tránh scope creep:

```text
KHÔNG xóa /api/v2
KHÔNG migrate toàn bộ Studio
KHÔNG rewrite Dashboard data
KHÔNG rewrite Episodes
KHÔNG rewrite Storyboard
KHÔNG rewrite Characters
KHÔNG rewrite Production
KHÔNG xóa FakeProductionApiClient
KHÔNG xóa Redux chỉ vì muốn dùng Zustand
KHÔNG xóa mock data hàng loạt
KHÔNG xóa old pages
KHÔNG dead-code cleanup lớn
KHÔNG redesign UI lần nữa
```

Những việc đó thuộc Phase 6–16.

---

# Chiến lược commit tôi đề xuất

Không thực hiện cả sáu phase trong một commit.

```text
P0
refactor/frontend-v3-p0-inventory

P1
refactor/frontend-v3-p1-domain-vocabulary

P2
refactor/frontend-v3-p2-api-foundation

P3
refactor/frontend-v3-p3-generated-client

P4
refactor/frontend-v3-p4-shared-app

P5
refactor/frontend-v3-p5-design-system
```

Mỗi phase:

```text
implementation commit(s)
        ↓
verification
        ↓
evidence commit
        ↓
phase verdict
```

Không sửa phase sau để che lỗi phase trước.

---

# Gate tổng sau Phase 0–5

Sau Phase 5 tôi chưa yêu cầu `/api/v2` hay mock bằng 0. Các invariant hợp lý ở **mốc foundation** là:

```text
Baseline inventory complete                    = YES
Canonical vocabulary unresolved                = 0

V3 common contract authority                   = 1
V3 ApiProblem formats                          = 1
V3 pagination conventions                      = 1
V3 concurrency conventions                     = 1
V3 idempotency conventions                     = 1
V3 event envelope conventions                  = 1

OpenAPI generation                             = PASS
generated TS contracts                         = PASS
generated API client                           = PASS
realtime package                               = PASS

new direct fetch violations since Phase 3      = 0
new handwritten V3 DTO duplication             = 0

Web importing Desktop App                      = 0
manual shell routing authority                 = 0
route manifests                                = 1

Web shared app build                           = PASS
Desktop shared app build                       = PASS

Design tokens authority                        = 1
shared primitive UI system                     = PASS
visual regression                              = PASS

existing V2 regression                         = PASS
existing Studio V3 regression                  = PASS
architecture checker                           = PASS
```

Verdict cuối:

```text
FRONTEND_V3_FOUNDATION_PHASE_0_5_VERIFIED
READY_FOR_PHASE_6_DASHBOARD_MONITORING
```

## Dependency thực tế

Tôi khuyến nghị **không chạy song song P0–P3**, vì đây là chuỗi authority:

```text
P0 Inventory
   ↓
P1 Vocabulary
   ↓
P2 API Contract
   ↓
P3 Generated Client
```

Sau khi P3 ổn định, **một phần P4 và P5 có thể chạy song song**:

```text
                  ┌─ P4 Router/App/Providers
P3 verified ──────┤
                  └─ P5 Tokens/UI primitives
```

nhưng **P5 integration vào AppShell nên merge sau khi skeleton P4 đã ổn định**.

Điểm kết thúc Phase 5 không phải là “frontend mới đã hoàn thành”, mà là **WindAgent đã có nền kiến trúc đủ sạch để Phase 6 trở đi migrate từng vertical slice mà không tiếp tục sinh thêm V2 client, mock fallback, direct `fetch()`, handwritten contract và routing riêng lẻ**. Đây là mốc nền tảng quan trọng nhất của toàn roadmap.
