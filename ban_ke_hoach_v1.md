# Kế hoạch P0 — WindAgent Feature Completion

**Baseline:** `cfa7ffb33fc1801ca8ad8115c605c320ddb4c51a`

Tôi đề xuất P0 không còn là một phase refactor. Đây sẽ là **Product Vertical Slice Completion**: lấy Architecture V3 hiện tại và biến nó thành một WindAgent Studio thực sự sử dụng được.

Gate cuối:

```text
WINDAGENT_P0_FEATURE_COMPLETE
```

P0 chỉ PASS khi người dùng có thể thực hiện toàn bộ:

```text
Configure Provider
        ↓
Test Connection
        ↓
Discover / Sync Models
        ↓
Configure Routing Rules
        ↓
Create Series
        ↓
Create Episode
        ↓
Enter Creative Brief
        ↓
Generate Ideas
        ↓
Select Idea
        ↓
Story Bible / World / Characters
        ↓
Beat Sheet
        ↓
Outline
        ↓
Screenplay
        ↓
Review
        ↓
Revision
        ↓
Optional Human Approval
        ↓
Lock
        ↓
READY_FOR_PRODUCTION
```

Và đường chạy phải là:

```text
Desktop/Web UI
   ↓
Shared frontend app
   ↓
API V3
   ↓
StudioApplicationService
   ↓
OrchestratorService
   ↓
Durable Queue
   ↓
Worker
   ↓
Model Router
   ↓
Provider
   ↓
Persistence
```

Không fake client, không direct handler invocation, không hard-coded artifact.

---

## 1. Trạng thái bắt đầu

P0 không bắt đầu từ số 0.

Provider backend đã có SQL authority, API key encrypted-at-rest, provider registration, real network connection test và model discovery.  Connection test cho durable provider thực sự gọi adapter và discovery, còn demo fallback đã bị giới hạn vào explicit demo profile.

Frontend hiện đã có chức năng add provider, nhập API key, test connection và tạo model rule. Tuy nhiên `ProvidersPage` hiện chỉ đơn giản render `RoutingPage`, cho thấy ranh giới Providers/Models/Routing vẫn chưa hoàn thiện ở mức sản phẩm.

Studio API cũng đã có create/list/get Series, create/list/get Episode, start/resume run, event stream, select idea, approval, revision và screenplay lock.

Episode frontend đã có `IdeaPanel`, `StoryBiblePanel`, `OutlinePanel`, `ScreenplayPanel`, `CheckpointReviewPanel` và pipeline UI.

Do đó P0 chủ yếu là:

```text
COMPLETE
+ CONNECT
+ HARDEN FEATURE SEMANTICS
+ REAL E2E
```

chứ không phải redesign architecture thêm lần nữa.

---

# 2. Phạm vi P0

| Workstream | Mục tiêu                           |
| ---------- | ---------------------------------- |
| P0-A       | Provider lifecycle hoàn chỉnh      |
| P0-B       | Model discovery/catalog hoàn chỉnh |
| P0-C       | Model routing hoàn chỉnh           |
| P0-D       | Series/Episode usable              |
| P0-E       | Story pipeline thực                |
| P0-F       | Review/Revision/Approval/Lock      |
| P0-G       | Desktop vertical workflow          |
| P0-H       | Functional E2E verification        |

Không thuộc P0:

```text
Blender rendering
Unreal production
automatic rigging
full asset generation
TTS production
final MP4
Browser Agent
general Agent Workspace
Memory redesign
Live Record completion
code-video certification
full Phase-16 certification
```

Các module đó giữ nguyên, không xóa.

---

# PHASE P0.0 — FEATURE TRUTH BASELINE

## Mục tiêu

Trước khi code, xác định chính xác cái gì:

```text
WORKING
PARTIAL
UI_ONLY
BACKEND_ONLY
STUB
BROKEN
NOT_REQUIRED_FOR_P0
```

### P0.0.1 Capture baseline

Ghi:

```text
HEAD
tree SHA
branch
dirty state

Python version
Node version
database backend

API tests
Studio tests
provider tests
worker tests
frontend tests
desktop build
```

Không cần chạy full Phase-16 certification.

### P0.0.2 Inventory P0 APIs

Đặc biệt:

```text
/api/v3/providers
/api/v3/models
/api/v3/routing

/api/v3/studio/series
/api/v3/studio/episodes
/api/v3/studio/runs
/api/v3/studio/artifacts
/api/v3/studio/... decisions
```

Xác định cho từng endpoint:

```text
UI consumer?
real persistence?
real runtime?
demo fallback?
stub?
missing mutation?
```

### P0.0.3 Freeze existing contracts

Studio request schemas hiện reuse canonical command contracts; không nên phá chúng tùy tiện.  Các command hiện đã chứa idempotency, optimistic version, artifact hash và revision lineage.

Nếu thiếu field presentation như:

```text
target audience
language
genre
tone
creative brief
target duration
constraints
```

P0 ưu tiên chuẩn hóa chúng trong `metadata` hiện hữu thay vì tạo contract V2 không cần thiết.

### Gate

```text
P0_0_FEATURE_TRUTH_CAPTURED
```

---

# PHASE P0.1 — PROVIDER MANAGEMENT

Đây nên là feature hoàn thiện đầu tiên vì Story pipeline phụ thuộc provider.

## Target UI

```text
Providers

[ Add Provider ]

OpenRouter
● Connected
Base URL: ...
Credential: configured
Models: 123
[Test Connection] [Sync Models] [Edit]

Google AI Studio
● Connected
...

Ollama
● Local
...
```

## P0.1.1 Provider lifecycle

Hoàn thiện:

```text
Create
Read
Edit
Enable / Disable
Credential rotate
Credential remove
Test connection
Delete
```

Delete phải fail nếu provider còn được model routing rule sử dụng, trừ khi người dùng xử lý dependency trước.

Không cascade silently.

## P0.1.2 Credential security

API key:

```text
write-only
encrypted at rest
never returned
never logged
never included in event payload
never committed to evidence
```

UI chỉ được biết:

```text
configured
not configured
credential label
last updated
```

## P0.1.3 Endpoint configuration

Tối thiểu:

```text
base URL
protocol mode
provider type
credential
enabled state
```

Protocol hiện đã có:

```text
OpenAI-compatible
Anthropic
Gemini
Ollama
```

ở frontend hiện tại.

MVP provider target:

```text
OpenRouter
Google AI Studio
Groq
Ollama
Custom OpenAI-compatible
```

OpenRouter và Groq có thể đi qua OpenAI-compatible adapter nếu implementation hiện tại cho phép; không tạo adapter riêng chỉ để có tên provider.

## P0.1.4 Connection test

Phải kiểm tra thật:

```text
DNS/network
authentication
base URL
protocol compatibility
model discovery
latency
```

Receipt:

```text
reachable
auth_valid
latency
models_found
error_code
message
checked_at
```

Backend đã có phần lớn contract này.

### Gate

```text
P0_1_PROVIDER_LIFECYCLE_LIVE
```

---

# PHASE P0.2 — MODEL DISCOVERY & MODEL CATALOG

Hiện Models page đã có canonical catalog, filter theo vendor/capability/local và hiển thị endpoint bindings/context.

P0 cần nối nó chặt với provider discovery.

## P0.2.1 Tách Test Connection khỏi Sync Models

Không nên phụ thuộc:

```text
Test Connection
    →
implicitly discover models
```

Target:

```text
Test Connection
Sync Models
```

là hai operation rõ ràng.

## P0.2.2 Durable discovered model registry

Model discovery phải persist:

```text
provider_id
endpoint_id
provider_model_id
canonical_model_id

display_name
capabilities
context_window

availability

pricing_class
input_price
output_price
currency

last_discovered_at
```

Pricing:

```text
FREE
PAID
UNKNOWN
```

**Không suy đoán pricing.**

Nếu provider không trả metadata pricing:

```text
UNKNOWN
```

## P0.2.3 Free / Paid controls

Đáp ứng UI Providers mà ta đã thiết kế trước đó:

```text
[Sync All]
[Get Free Models]
[Get Paid Models]
```

Nhưng semantics:

* Provider có pricing API thật → dùng server-side filter.
* Provider chỉ trả model list → sync trước, filter metadata đã biết.
* Không có pricing authority → hiển thị UNKNOWN, không tự gắn Paid/Free.

## P0.2.4 Discovery reconciliation

Một lần sync phải phân loại:

```text
ADDED
UPDATED
UNCHANGED
UNAVAILABLE
```

Không xóa model ngay chỉ vì một lần discovery không thấy nó.

Dùng trạng thái:

```text
active
unavailable
deprecated
```

## P0.2.5 Model probe

Cho phép:

```text
[Test Model]
```

Thực hiện một inference nhỏ thật để xác minh:

```text
endpoint
credential
model ID
protocol
response
```

Không dùng test này để benchmark chất lượng.

### Gate

```text
P0_2_MODEL_CATALOG_LIVE
```

---

# PHASE P0.3 — ROUTING RULES

Đây là phần quyết định model nào làm từng bước Story.

Backend hiện đã support durable rule gồm primary model, fallback model, priority và role.

P0 cần nâng nó từ một form nhập ID thủ công thành router usable.

## P0.3.1 Canonical Story roles

Tối thiểu:

```text
studio.story.idea.generate
studio.story.idea.evaluate

studio.story.bible.generate

studio.story.beats.generate
studio.story.outline.generate

studio.story.screenplay.generate
studio.story.screenplay.review
studio.story.screenplay.revise
```

Lock không cần LLM.

## P0.3.2 Mỗi rule là một resource độc lập

Ví dụ:

```text
Rule: Screenplay Writer
Role:
studio.story.screenplay.generate

Primary:
Gemini ...

Fallback:
DeepSeek ...

Enabled:
true

Priority:
10
```

Không có một global object chứa hàng loạt hard-coded model names.

## P0.3.3 Không nhập canonical ID bằng text

Current UI đang bắt người dùng nhập:

```text
Discovered canonical model id
```

thủ công.

P0 phải chuyển thành:

```text
Provider selector
    ↓
Model selector
```

lấy trực tiếp từ Model Catalog.

## P0.3.4 Resolution order

Target:

```text
exact role rule
      ↓
capability/default rule
      ↓
system default
      ↓
FAIL CLOSED
```

Không tìm thấy model hợp lệ:

```text
ROUTING_UNAVAILABLE
```

không tự chọn model ngẫu nhiên.

## P0.3.5 Fallback

Fallback chỉ xảy ra với các failure được định nghĩa:

```text
endpoint unavailable
timeout
rate limit
temporary provider failure
```

Không fallback khi:

```text
schema validation failure
bad prompt contract
business rule violation
invalid artifact
```

## P0.3.6 Route receipt

Mỗi LLM task persist:

```text
task_id
role
rule_id

selected_provider
selected_model

fallback_used
fallback_reason

started_at
completed_at
```

Điều này cực kỳ quan trọng để sau này debug chất lượng Story.

### Gate

```text
P0_3_MODEL_ROUTING_LIVE
```

---

# PHASE P0.4 — SERIES & EPISODE PRODUCT COMPLETION

API Series/Episode hiện đã có create/list/get.

P0 cần biến chúng thành usable product resources.

## Series metadata authority

Chuẩn hóa:

```text
title
description

target_audience
language
genre
tone

narrative_style
content_constraints

approval_policy
```

Vì command hiện hỗ trợ `metadata`, P0 có thể sử dụng schema metadata được validate thay vì phá `studio.command/v1`.

## Episode metadata

```text
title
episode_number

logline
creative_brief

target_duration
target_audience

episode_constraints
```

## Required operations

```text
Create Series
List Series
Open Series
Edit Series metadata

Create Episode
List Episodes
Open Episode
Edit draft Episode metadata
```

Sau khi Story run bắt đầu, các field ảnh hưởng generation phải có semantics rõ ràng:

```text
either immutable
or generate new revision
```

Không silently mutate context của run đang tồn tại.

## P0.4.1 Preflight

Trước nút:

```text
Start Story
```

server kiểm tra:

```text
Episode exists
Creative brief valid
Provider configured
Required routing rules resolve
Worker capability available
Persistence available
```

Nếu thiếu:

```text
START_BLOCKED
```

kèm lý do rõ ràng.

### Gate

```text
P0_4_STUDIO_PROJECTS_USABLE
```

---

# PHASE P0.5 — REAL STORY PIPELINE

Đây là core của P0.

## Canonical DAG

```text
idea.generate
     ↓
idea.evaluate
     ↓
WAIT_FOR_IDEA_SELECTION
     ↓
bible.generate
     ↓
beats.generate
     ↓
outline.generate
     ↓
screenplay.generate
     ↓
screenplay.review
```

Không bypass Worker.

## P0.5.1 Inputs

Mỗi task phải nhận input từ authoritative artifacts:

```text
Series metadata
Episode creative brief
Selected idea
Story Bible
World/Character canon
previous artifact
revision lineage
```

Không đọc ngầm state global.

## P0.5.2 Structured outputs

Mỗi LLM output:

```text
Provider raw response
       ↓
parser
       ↓
schema validator
       ↓
domain validator
       ↓
artifact
```

Nếu invalid:

```text
TASK_FAILED
```

hoặc controlled repair.

Không persist garbage artifact rồi tiếp tục DAG.

## P0.5.3 Durable artifact chain

Mỗi artifact phải có:

```text
artifact_id
artifact_type

series_id
episode_id
revision_id

parent/input hashes
content_hash

created_at
creator/task

schema_version
```

## P0.5.4 Pause/resume

Đã có `start_or_resume_run`.

P0 phải xác nhận:

```text
process crash
API restart
worker restart
user close desktop
```

không làm mất run.

Resume không chạy lại task đã successfully committed.

## P0.5.5 Idea selection

Flow:

```text
Generate candidates
        ↓
Persist candidate set
        ↓
Pause
        ↓
User selects candidate
        ↓
CAS / optimistic version check
        ↓
Resume DAG
```

Command hiện đã có:

```text
revision_id
candidate_id
expected_content_hash
expected_optimistic_version
```

nên giữ nguyên semantics này.

### Gate

```text
P0_5_STORY_DAG_REAL
```

---

# PHASE P0.6 — REVIEW → REVISION → APPROVAL → LOCK

## Review

Review artifact tối thiểu cần:

```text
overall score

plot
character
continuity
pacing
dialogue
audience fit
production feasibility

findings
severity
evidence
suggested correction
```

Review phải là data, không chỉ free-text.

## Revision

Nếu review yêu cầu sửa:

```text
Screenplay Revision N
         ↓
Review
         ↓
Revision N+1
```

Phải bounded.

Không có infinite autonomous loop.

## Approval policy

Support:

```text
AUTO
REQUIRE_HUMAN
CONDITIONAL
```

Ví dụ conditional:

```text
review has blocking finding
score below threshold
large revision
```

## Approval

Current command đã bind decision với:

```text
revision
checkpoint
artifact_hash
actor
optimistic_version
```

đây là đúng direction và phải giữ.

## Lock

Lock chỉ PASS nếu:

```text
correct episode
correct revision
correct screenplay hash

review requirements satisfied
approval requirements satisfied

not already superseded
optimistic version matches
```

Sau lock:

```text
SCREENPLAY_LOCKED
        ↓
READY_FOR_PRODUCTION
```

## P0.6.1 Sửa semantic `issued_at`

Lỗi timestamp synthetic mà ta phát hiện trong `cfa7ffb...` nên được sửa ở đây, không đợi Phase 16.

Production:

```text
issued_at = actual persisted approval/lock time
```

Test:

```text
inject deterministic Clock
```

Không derive timestamp từ content hash.

Đây là **feature correctness**, không chỉ certification cleanup.

## P0.6.2 Immutability

Sau lock:

```text
screenplay cannot mutate
```

Muốn sửa:

```text
derive revision
```

không unlock object cũ.

### Gate

```text
P0_6_SCREENPLAY_LOCK_SEMANTICS_VERIFIED
```

---

# PHASE P0.7 — FRONTEND PRODUCT CONVERGENCE

Frontend architecture hiện đã đủ tốt. Không redesign framework nữa.

## Providers

`ProvidersPage` không còn chỉ alias `RoutingPage`.

Tách product surfaces:

```text
Providers
    provider / endpoint / API key / connection

Models
    discovered catalog / free-paid / capabilities

Routing
    task role → model rule
```

## Studio Home

```text
New Series

Active Series
Episodes in progress
Pending approval
Ready for Production
```

Không fake metrics.

## Series

```text
Series info
Episodes
Create Episode
Open Episode
```

## Episode Workspace

Reuse những component đã tồn tại:

```text
EpisodePipeline
IdeaPanel
StoryBiblePanel
OutlinePanel
ScreenplayPanel
CheckpointReviewPanel
```

Bổ sung only missing integration.

## Actions

UI expose theo server state:

```text
Start
Select Idea
Resume
Approve
Reject
Request Revision
Lock
```

Không frontend tự quyết state transition.

## Required UX states

```text
loading
running
waiting for input
waiting approval
failed
retrying
locked
ready
offline
provider unavailable
```

### Gate

```text
P0_7_DESKTOP_VERTICAL_FLOW_LIVE
```

---

# PHASE P0.8 — FUNCTIONAL E2E ACCEPTANCE

Đây chưa phải Phase-16 certification.

Mục đích đơn giản:

> WindAgent có làm được công việc thật không?

## Scenario A — Auto approval

```text
Provider configured
↓
Models discovered
↓
Rules configured
↓
Create Series
↓
Create Episode
↓
Generate
↓
Select Idea
↓
Story
↓
Outline
↓
Screenplay
↓
Review PASS
↓
Lock
↓
READY_FOR_PRODUCTION
```

## Scenario B — Human approval

```text
...
Review
↓
WAITING_FOR_APPROVAL
↓
Approve
↓
Lock
```

## Scenario C — Revision

```text
Review finds issue
↓
Revision
↓
Review again
↓
Approval
↓
Lock
```

## Scenario D — Provider failure

```text
Primary provider failure
↓
router determines fallback allowed
↓
fallback model
↓
route receipt records fallback
↓
pipeline continues
```

## Scenario E — Restart recovery

During pipeline:

```text
kill Worker
restart Worker
```

Expected:

```text
run resumes
no duplicate artifacts
no duplicate state transition
```

---

# 3. Test matrix P0

| Layer                            | Required                        |
| -------------------------------- | ------------------------------- |
| Provider unit                    | PASS                            |
| Provider API contract            | PASS                            |
| Credential security              | PASS                            |
| Model discovery                  | PASS                            |
| Model reconciliation             | PASS                            |
| Routing resolution               | PASS                            |
| Routing fallback                 | PASS                            |
| Series/Episode                   | PASS                            |
| Story artifact validation        | PASS                            |
| Story DAG                        | PASS                            |
| Run resume                       | PASS                            |
| Idea CAS                         | PASS                            |
| Review/revision                  | PASS                            |
| Approval                         | PASS                            |
| Lock immutability                | PASS                            |
| Frontend feature tests           | PASS                            |
| Desktop typecheck                | PASS                            |
| Desktop build                    | PASS                            |
| SQLite integration               | PASS                            |
| PostgreSQL Studio vertical slice | PASS                            |
| Real-provider smoke              | PASS or `SKIPPED_NO_CREDENTIAL` |

`SKIPPED_NO_CREDENTIAL` không được tính thành PASS.

Không cần ở P0:

```text
full repository certification
36-suite Phase16 matrix
full Blender regression
final evidence attestation
```

---

# 4. Thứ tự thực hiện

```text
P0.0 Feature Truth
          │
          ├─────────────────┐
          ↓                 ↓
P0.1 Providers        P0.4 Series/Episode
          │                 │
          ↓                 │
P0.2 Models                 │
          │                 │
          ↓                 │
P0.3 Routing                │
          └────────┬────────┘
                   ↓
             P0.5 Story DAG
                   ↓
        P0.6 Review / Revision /
             Approval / Lock
                   ↓
             P0.7 Frontend
                   ↓
             P0.8 Real E2E
                   ↓
       WINDAGENT_P0_FEATURE_COMPLETE
```

Frontend không nhất thiết đợi P0.6 mới bắt đầu. UI của feature nào backend contract đã ổn thì có thể triển khai song song.

---

# 5. Quy tắc code trong P0

Không thêm architecture layer mới nếu existing layer giải quyết được vấn đề.

Ưu tiên:

```text
FIX EXISTING FEATURE
        >
NEW ABSTRACTION
```

và:

```text
existing contract
        >
new duplicate contract

existing service
        >
parallel service

real persistence
        >
frontend/local state

server authority
        >
frontend inference

real provider
        >
demo receipt
```

Không được vì test determinism mà thay đổi semantics production.

---

# 6. Commit strategy

Tôi khuyên chia P0 thành các commit/PR độc lập:

```text
feat(p0-provider): complete provider lifecycle

feat(p0-models): durable discovery and catalog sync

feat(p0-routing): story model routing rules

feat(p0-studio): complete series and episode inputs

feat(p0-story): complete real story DAG

feat(p0-review): revision approval and lock semantics

feat(p0-ui): complete studio vertical workflow

test(p0): real functional vertical slice

docs(p0): feature-complete handoff
```

Không tạo thêm commit kiểu:

```text
provider + story + UI + evidence + unrelated code-video
```

như vấn đề atomicity ở commit hiện tại.

---

# 7. Definition of Done cuối P0

P0 chỉ được đóng khi:

```text
[PASS] API key có thể cấu hình an toàn
[PASS] Provider test thật
[PASS] Models sync thật
[PASS] Free/Paid/Unknown truthful
[PASS] Model rules persist
[PASS] Worker sử dụng đúng durable rules
[PASS] Series chạy thật
[PASS] Episode chạy thật
[PASS] Story DAG chạy qua durable worker
[PASS] Idea selection pause/resume thật
[PASS] Story artifacts persist
[PASS] Screenplay generated thật
[PASS] Review thật
[PASS] Revision lineage đúng
[PASS] Human approval hoạt động
[PASS] Screenplay lock immutable
[PASS] READY_FOR_PRODUCTION đạt được
[PASS] Desktop thực hiện được toàn bộ flow
[PASS] restart không làm mất run
[PASS] PostgreSQL vertical slice
[PASS] không hard-coded success
```

**Không yêu cầu Phase-16 certification phải PASS để đóng P0.**

Sau P0, trạng thái dự án nên là:

```text
ARCHITECTURE V3
      +
FEATURE COMPLETE STORY STUDIO
      +
REAL PROVIDER ROUTING
      +
REAL DURABLE STORY PIPELINE
      +
USABLE DESKTOP
```

Sau đó mới chuyển sang **P1: Characters / World / Assets / Storyboard / Production handoff**, rồi cuối cùng mới làm một đợt hardening + certification toàn repo.
