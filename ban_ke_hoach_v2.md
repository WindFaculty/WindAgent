Dựa trên roadmap trong tài liệu bạn gửi và đối chiếu trực tiếp repository `WindFaculty/WindAgent` tại snapshot **`ac2c19c59ca3c16c86e81d761c0a70b911bb294e`**, tôi sẽ coi **Phase 0–5 là foundation đã được hoàn thành/đạt gate trước khi bắt đầu phần này**. Commit đó đúng là snapshot được dùng trong báo cáo, và bản thân commit chủ yếu thêm công cụ tải Stitch chứ chưa thực hiện migration frontend. 

# Roadmap chi tiết — Phase 6 → Phase 10

## 0. Dependency graph

```text
Phase 0–5
API V3 foundation
Generated Client
Router/App Foundation
Design System
       │
       ▼
┌────────────────────────────┐
│ PHASE 6                    │
│ Dashboard + Monitoring     │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│ PHASE 7                    │
│ Projects + Studio          │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│ PHASE 8                    │
│ Episode Workspace          │
│ Story → Screenplay         │
└─────────────┬──────────────┘
              │
              ▼
       PHASE 9.0
 Shared Story Production
       Contracts
              │
     ┌────────┼────────┬────────┬────────┐
     ▼        ▼        ▼        ▼        ▼
    9A       9B       9C       9D       9E
Characters World Storyboard Reviews Assets
     │        │        │        │        │
     └────────┴────────┴────────┴────────┘
                       │
                       ▼
┌────────────────────────────┐
│ PHASE 10                   │
│ Production                 │
│ Shot → Audio → Render      │
└────────────────────────────┘
```

**Phase 9A–9E là nhóm duy nhất nên chạy song song mạnh.** Phase 6 → 7 → 8 nên tuần tự, vì Phase 6 đóng vai trò proving ground cho Query + generated client + realtime + routing mà Phase 7/8 sẽ tái sử dụng.

---

# PHASE 6 — Dashboard + Monitoring Production Cutover

## Mục tiêu

Biến Dashboard từ UI có dữ liệu mô phỏng thành **observability surface chạy hoàn toàn bằng runtime data thật**, đồng thời tạo Monitoring page làm nguồn quan sát hệ thống chuyên sâu.

Đây là phase kiểm chứng toàn bộ foundation từ Phase 2–5.

Snapshot hiện tại cho thấy `Dashboard.tsx` vẫn chứa model distribution, chart datasets, KPI giả và manual refresh sử dụng `Math.random()`. `App.tsx` lại polling health mỗi 5 giây, metrics mỗi 2 giây và Web fallback sang số liệu random.

## 6.0 — Preflight

Trước khi sửa code:

```text
git status
current SHA
OpenAPI generation PASS
frontend typecheck PASS
frontend unit tests PASS
backend tests PASS
web build PASS
desktop build PASS
```

Lưu:

```text
artifacts/frontend_restructure/phase_06/baseline/
├── commit.json
├── test_baseline.json
├── api_contract_baseline.json
├── dashboard_runtime_inventory.json
├── synthetic_data_inventory.json
└── baseline.md
```

Phải inventory toàn bộ:

```text
Math.random()
setInterval
setTimeout
hardcoded KPI
hardcoded model usage
hardcoded chart data
Tauri get_system_metrics
health polling
```

---

## 6.1 — Canonical monitoring contract

Backend trở thành authority cho dữ liệu observability.

Tạo V3 API:

```http
GET /api/v3/dashboard/summary

GET /api/v3/system/metrics
GET /api/v3/system/health

GET /api/v3/monitoring/workers
GET /api/v3/monitoring/providers
GET /api/v3/monitoring/agents
GET /api/v3/monitoring/queues
GET /api/v3/monitoring/runs
```

Realtime:

```text
/ws/v3/system/metrics
/ws/v3/events
```

Không để Desktop và Web có hai định nghĩa CPU/GPU khác nhau.

Canonical payload:

```ts
SystemMetrics {
    sampled_at
    cpu
    memory
    gpu[]
    disk
    process
}

GpuMetrics {
    id
    name
    utilization_percent
    temperature_c
    memory_used_bytes
    memory_total_bytes
}
```

Với máy không có GPU metrics:

```text
supported = false
```

không được giả số liệu.

---

## 6.2 — Dashboard summary service

Tạo application query tập hợp:

```text
projects
episodes
active runs
agents
models/providers
recent activity
system status
storage
```

Ví dụ:

```http
GET /api/v3/dashboard/summary
```

trả về:

```text
projects.total
episodes.total
episodes.active
runs.running
runs.failed
agents.running
agents.total
providers.healthy
providers.total
activity
model_usage
storage
```

Không để Dashboard tự fetch 8 endpoint rồi tự tổng hợp business metrics.

---

## 6.3 — Frontend feature

Target:

```text
frontend/app/src/features/dashboard/
├── pages/
│   └── DashboardPage.tsx
├── components/
│   ├── StudioSummaryCards.tsx
│   ├── SystemResourceCards.tsx
│   ├── StudioActivityChart.tsx
│   ├── ModelUsagePanel.tsx
│   ├── AgentSwarmSummary.tsx
│   ├── RecentActivityFeed.tsx
│   └── StorageSummary.tsx
├── hooks/
│   ├── useDashboardSummary.ts
│   └── useSystemMetrics.ts
└── model/
```

Và:

```text
frontend/app/src/features/monitoring/
├── MonitoringPage.tsx
├── ResourceMetrics.tsx
├── WorkerStatus.tsx
├── QueueMetrics.tsx
├── ProviderHealth.tsx
├── AgentMetrics.tsx
├── RuntimeMetrics.tsx
└── hooks/
```

---

## 6.4 — Loại state khỏi `App`

`App.tsx` không còn sở hữu:

```text
metrics
setMetrics
refreshInterval
setRefreshInterval
health polling
Tauri get_system_metrics
```

`DashboardPage` không còn props kiểu:

```tsx
metrics={...}
setMetrics={...}
setActiveTab={...}
```

Navigation sử dụng router:

```ts
navigate("/studio/projects")
```

Manual refresh chỉ:

```ts
queryClient.invalidateQueries(...)
```

không sinh số liệu mới.

---

## 6.5 — Realtime metrics

Luồng:

```text
System Metrics Collector
          ↓
Event Publisher
          ↓
WebSocket
          ↓
RealtimeClient
          ↓
Query Cache
          ↓
Dashboard / Monitoring
```

Bắt buộc test:

```text
disconnect
reconnect
duplicate event
out-of-order event
sequence gap
backend restart
page refresh
WebSocket unavailable
```

Nếu realtime unavailable:

```text
WS → HTTP snapshot
```

được phép fallback.

Không fallback thành mock.

---

## 6.6 — Monitoring route

Canonical routes:

```text
/dashboard
/monitoring
```

Dashboard chỉ summary.

Monitoring mới chứa:

```text
CPU
RAM
GPU
VRAM
workers
queue depth
running jobs
agents
provider latency
provider errors
API latency
recent failures
```

---

## 6.7 — Tests

Unit:

```text
DashboardSummaryCards
SystemResourceCards
ModelUsagePanel
useDashboardSummary
useSystemMetrics
```

Contract:

```text
dashboard summary schema
system metric schema
metrics websocket envelope
```

E2E:

```text
open /dashboard
→ real summary rendered
→ open /monitoring
→ metrics received
→ backend reconnect
→ page recovers
```

Test Web và Tauri.

---

## Phase 6 gate

Bắt buộc:

```text
Math.random() runtime metrics          = 0
synthetic dashboard KPI                = 0
Dashboard-owned system polling         = 0
direct fetch                           = 0
generated API client                   = PASS
realtime reconnect test                = PASS
Web dashboard                          = PASS
Desktop dashboard                      = PASS
Monitoring                             = PASS
visual regression                      = PASS
```

Evidence:

```text
artifacts/frontend_restructure/phase_06/final/
```

Final verdict:

```text
FRONTEND_V2_PHASE_06_DASHBOARD_MONITORING_VERIFIED
```

---

# PHASE 7 — Projects + Studio Convergence

## Mục tiêu

Hợp nhất hai implementation đang chồng lấn:

```text
StudioPage
ProjectsPage
```

thành một architecture thống nhất:

```text
Studio Home
    ↓
Projects
    ↓
Project Detail
    ↓
Episodes
```

Hiện cả `StudioPage` và `ProjectsPage` đều tự khởi tạo `HttpStudioApiClient + StudioStore`; Studio còn tự parse hash và quản lý mutation/local state.

---

## 7.0 — Chốt Project vs Series

Đây là hard gate.

Nếu ADR Phase 1 đã chọn:

```text
Project
```

thì frontend không được tiếp tục lan truyền `Series`.

Có thể backend tạm thời vẫn map:

```text
Project facade
      ↓
existing StudioSeries service
```

nhưng V3 contract phải dùng vocabulary canonical.

Ví dụ:

```http
GET  /api/v3/projects
POST /api/v3/projects

GET   /api/v3/projects/:projectId
PATCH /api/v3/projects/:projectId

GET  /api/v3/projects/:projectId/episodes
POST /api/v3/projects/:projectId/episodes
```

Không cần rewrite domain implementation ngay.

---

## 7.1 — Generated project client

Operation IDs:

```text
projects.list
projects.get
projects.create
projects.update

episodes.listForProject
episodes.create
```

Frontend tuyệt đối không tạo:

```text
Date.now()
Math.random()
```

để làm idempotency key.

Shared transport tự sinh:

```http
Idempotency-Key: UUID
```

---

## 7.2 — Projects feature

```text
features/projects/
├── pages/
│   ├── ProjectsPage.tsx
│   └── ProjectDetailPage.tsx
├── components/
│   ├── ProjectCard.tsx
│   ├── ProjectList.tsx
│   ├── ProjectFilters.tsx
│   ├── CreateProjectDialog.tsx
│   ├── CreateEpisodeDialog.tsx
│   └── ProjectTemplatePicker.tsx
└── hooks/
    ├── useProjects.ts
    ├── useProject.ts
    ├── useCreateProject.ts
    └── useCreateEpisode.ts
```

State:

```text
projects                → TanStack Query
project                  → TanStack Query
search/filter/sort       → URL search params
dialog open/closed       → local UI state
form                     → form state
```

---

## 7.3 — Studio Home

Studio Home không còn làm router + API + workflow engine.

Nó chỉ hiển thị:

```text
recent projects
recent episodes
pipeline activity
create project
continue episode
```

Route:

```text
/studio
/studio/projects
/studio/projects/:projectId
```

---

## 7.4 — StudioStore migration

Không xóa package ngay.

Phase 7 chỉ:

```text
ProjectsPage → remove StudioStore
StudioHome   → remove StudioStore
ProjectDetail→ remove StudioStore
```

Episode flow cũ vẫn có thể giữ `StudioStore` đến Phase 8.

Sau Phase 8 mới có thể đạt:

```text
production StudioStore consumers = 0
```

rồi giữ package dead cho Phase 16 cleanup.

---

## 7.5 — Capability handling

Capabilities không được load thủ công ở từng page.

Tạo:

```ts
useCapabilities()
```

hoặc:

```ts
useSystemCapabilities()
```

Cache dùng chung toàn application.

Các nút chỉ disabled khi capability thật unavailable.

Không fake-success.

---

## 7.6 — Project templates

Các template hiện có thể giữ lại nếu được xác định là **template sản phẩm thực**, nhưng phải chuyển khỏi component:

```text
frontend static template registry
```

hoặc backend:

```http
GET /api/v3/project-templates
```

Không coi chúng là runtime project data.

---

## 7.7 — E2E

Critical flow:

```text
Open Projects
      ↓
Create Project
      ↓
Project appears from server
      ↓
Open Project
      ↓
Create Episode
      ↓
Episode persisted
      ↓
Refresh browser
      ↓
Project + Episode still exist
```

Thêm:

```text
duplicate submission test
409 expected_version test
network failure
404
500
empty state
```

---

## Phase 7 gate

```text
StudioStore in Projects              = 0
StudioStore in Studio Home           = 0
manual hash parsing there            = 0
direct fetch                         = 0
duplicate client construction        = 0
Project/Series vocabulary conflict   = 0 in new frontend
Create Project E2E                   = PASS
Create Episode E2E                   = PASS
reload persistence                   = PASS
Web                                  = PASS
Desktop                              = PASS
```

Verdict:

```text
FRONTEND_V2_PHASE_07_PROJECTS_STUDIO_VERIFIED
```

---

# PHASE 8 — Canonical Episode Workspace

Đây là **phase quan trọng nhất của frontend mới**, vì đây chính là workflow tạo kịch bản cốt lõi của WindAgent.

`EpisodesPage` hiện vẫn là mock dataset `DEFAULT_EPISODES`; tạo Episode chỉ thêm object vào React state.

## Mục tiêu cuối

```text
Project
   ↓
Episode
   ↓
┌──────────────────────────────┐
│ Episode Workspace            │
│                              │
│ Idea                         │
│ Story Bible                  │
│ Beats                        │
│ Outline                      │
│ Screenplay                   │
│ Review                       │
│ Lock                         │
│ Storyboard                   │
│ Production                   │
└──────────────────────────────┘
```

Một workspace, một route context, một source of truth.

---

## 8.0 — Episode contract

Canonical fields tối thiểu:

```text
id
project_id
title
description
state
current_checkpoint
current_revision_id
optimistic_version
created_at
updated_at
```

Không lưu `progress = 65` như một mutable UI field.

Progress phải derive từ pipeline state.

---

## 8.1 — APIs

```http
GET    /api/v3/episodes/:id
PATCH  /api/v3/episodes/:id
DELETE /api/v3/episodes/:id

GET /api/v3/episodes/:id/artifacts
GET /api/v3/episodes/:id/revisions
GET /api/v3/episodes/:id/runs
```

Commands:

```text
episodes.startGeneration
episodes.selectIdea
episodes.requestRevision
episodes.approveCheckpoint
episodes.lockScreenplay
episodes.cancelRun
```

---

## 8.2 — Workspace route

```text
/studio/episodes/:episodeId
/studio/episodes/:episodeId/idea
/studio/episodes/:episodeId/story
/studio/episodes/:episodeId/outline
/studio/episodes/:episodeId/screenplay
/studio/episodes/:episodeId/review
/studio/episodes/:episodeId/storyboard
/studio/episodes/:episodeId/production
```

Parent loader/query chịu trách nhiệm Episode context.

Tabs không tự fetch cùng Episode lại.

---

## 8.3 — Feature architecture

```text
features/episodes/
├── pages/
│   ├── EpisodesPage.tsx
│   └── EpisodeWorkspacePage.tsx
│
├── workspace/
│   ├── IdeaPanel.tsx
│   ├── StoryBiblePanel.tsx
│   ├── BeatsPanel.tsx
│   ├── OutlinePanel.tsx
│   ├── ScreenplayPanel.tsx
│   ├── CheckpointReviewPanel.tsx
│   └── EpisodePipeline.tsx
│
├── components/
│   ├── EpisodeCard.tsx
│   ├── EpisodeStatus.tsx
│   ├── RevisionSelector.tsx
│   └── RunProgress.tsx
│
└── hooks/
```

---

## 8.4 — Revision authority

Mọi approval phải gắn vào immutable revision.

Ví dụ:

```json
{
  "episode_id": "...",
  "revision_id": "...",
  "decision": "APPROVED",
  "expected_version": 8
}
```

Không approve "screenplay hiện tại" một cách mơ hồ.

Lock cũng phải xác định:

```text
revision_id
content_hash
expected_version
```

Ý tưởng này hiện đã xuất hiện trong Studio implementation và nên được giữ khi chuyển sang V3 canonical client.

---

## 8.5 — Episode realtime

Events:

```text
episode.updated
run.started
run.progress
run.failed
run.completed

artifact.created
revision.created

checkpoint.awaiting_approval
checkpoint.approved
checkpoint.revision_requested

screenplay.locked
```

Query cache update trực tiếp từ events.

Không polling Episode 2–5 giây.

---

## 8.6 — Conflict handling

Case bắt buộc:

```text
Client A opens version 7
Client B approves version 7 → server becomes 8
Client A tries approval expected_version=7
                       ↓
                     409
                       ↓
invalidate/refetch
                       ↓
show conflict state
```

Không silently retry mutation.

---

## 8.7 — Deep link/recovery

Phải test:

```text
refresh page mid-generation
close/reopen desktop
open direct episode URL
backend restarts
WS disconnected
event sequence gap
```

UI phải recover từ server snapshot.

---

## 8.8 — Critical certification flow

Đây là E2E quan trọng nhất Phase 8:

```text
Create Project
      ↓
Create Episode
      ↓
Start Generation
      ↓
Ideas generated
      ↓
Select Idea
      ↓
Story Bible
      ↓
Approve
      ↓
Outline
      ↓
Approve
      ↓
Screenplay
      ↓
Review
      ↓
Approve
      ↓
Lock Screenplay
      ↓
READY_FOR_PRODUCTION
```

Không được mock bất kỳ checkpoint nào.

---

## Phase 8 gate

```text
DEFAULT_EPISODES runtime              = 0
local-only episode creation           = 0
manual StudioStore instance           = 0
manual hash parsing                   = 0
polling episode state                 = 0
generated V3 client                   = PASS
revision conflict                     = PASS
reconnect/resume                      = PASS
full screenplay E2E                   = PASS
Web                                   = PASS
Desktop                               = PASS
```

Verdict:

```text
FRONTEND_V2_PHASE_08_EPISODE_WORKSPACE_VERIFIED
```

---

# PHASE 9 — Story Production Domain

Phase này nên chia thành:

```text
9.0 Shared contracts
9A Characters
9B World
9C Storyboard
9D Reviews
9E Assets
9F Integration certification
```

Sau **9.0 PASS**, 9A–9E có thể triển khai song song.

---

# Phase 9.0 — Shared contract freeze

Trước khi chia worker, freeze:

```text
Project ID
Episode ID
Revision ID
Character ID
Location ID
Scene ID
Asset ID
Review ID
Generation Job ID
```

Và relationship:

```text
Project
 ├── Character
 ├── World
 └── Episode
       ├── ScreenplayRevision
       ├── Storyboard
       │     └── Scene[]
       ├── Review[]
       └── Asset[]
```

Nếu không freeze trước, năm nhánh sẽ tự phát minh schema khác nhau.

---

# Phase 9A — Characters

`CharactersPage` hiện dùng toàn bộ `DEFAULT_CHARACTERS` và thao tác create chỉ thêm vào React state.

Target:

```text
features/characters/
├── CharactersPage
├── CharacterDetailPage
├── CharacterEditor
├── CharacterRelationships
├── CharacterVisualProfile
├── CharacterVoiceProfile
└── CharacterAssets
```

API:

```http
GET  /api/v3/projects/:projectId/characters
POST /api/v3/projects/:projectId/characters

GET   /api/v3/characters/:id
PATCH /api/v3/characters/:id
DELETE /api/v3/characters/:id

GET /api/v3/characters/:id/relationships
GET /api/v3/characters/:id/assets
```

Canonical model:

```text
identity
role
biography
psychology
visual_profile
voice_profile
relationships
revision
```

Character references trong screenplay/storyboard phải dùng ID, không dùng tên tự do.

---

# Phase 9B — World

Đây gần như feature mới hoàn toàn.

Route:

```text
/studio/projects/:projectId/world
```

Model:

```text
World
Locations
Factions
Lore
Timeline
Rules
VisualReferences
```

API:

```text
world.get
world.update

locations.list/create/update
factions.list/create/update
lore.list/create/update
```

Story agents phải có thể consume World Bible bằng domain service, không scrape UI representation.

---

# Phase 9C — Storyboard

Snapshot hiện tại dùng `DEFAULT_SCENES`; Generate Art chỉ đổi state sang `Generating`, chờ `setTimeout(2000)` rồi gán một ảnh cố định.

Target:

```text
Screenplay locked revision
         ↓
Storyboard generation
         ↓
Scene records
         ↓
Concept generation jobs
         ↓
Generated asset revision
```

API:

```http
GET  /api/v3/episodes/:id/storyboard
POST /api/v3/episodes/:id/storyboard/actions/sync

POST /api/v3/storyboard/scenes
PATCH /api/v3/storyboard/scenes/:sceneId

POST /api/v3/storyboard/scenes/:sceneId/generations
```

Generation phải trả:

```text
generation_id
status
submitted_at
```

Sau đó realtime:

```text
generation.queued
generation.started
generation.progress
generation.completed
generation.failed
```

**Không timer giả.**

Scene phải ghi:

```text
source_screenplay_revision_id
```

để tránh storyboard được sinh từ screenplay cũ.

---

# Phase 9D — Reviews

`ReviewsPage` hiện sử dụng `DEFAULT_VERSIONS`, `DEFAULT_COMMENTS`; Approve/Revision chỉ đổi local state.

Phase 8 đã xử lý **checkpoint approval của screenplay**.

Phase 9D mở rộng thành generic review system cho:

```text
storyboard
character revision
asset revision
production preview
```

Canonical:

```text
Review
ReviewSubject
ReviewComment
ReviewDecision
Revision
```

Decision:

```json
{
  "decision": "APPROVED",
  "revision_id": "...",
  "expected_version": 12,
  "reason": "..."
}
```

Không approve mutable object.

---

# Phase 9E — Assets

Migrate khỏi:

```text
/api/v2/video-production/assets
```

sang canonical:

```http
GET  /api/v3/assets
POST /api/v3/assets

GET /api/v3/assets/:id

GET /api/v3/assets/:id/revisions
GET /api/v3/assets/:id/provenance
GET /api/v3/assets/:id/dependencies

POST /api/v3/assets/:id/actions/approve
POST /api/v3/assets/:id/actions/reject
```

Storage phải durable.

Asset cần provenance:

```text
source
generator
model
prompt/reference
job_id
created_at
parent_revision
content_hash
```

Đặc biệt quan trọng sau này khi Blender agents tái sử dụng asset.

---

# Phase 9F — Integration certification

Sau khi 9A–9E merge:

```text
Project
   ↓
Character + World
   ↓
Episode
   ↓
Locked Screenplay
   ↓
Storyboard sync
   ↓
Scene
   ↓
Concept Generation
   ↓
Asset
   ↓
Review
   ↓
Approved Asset
```

Kiểm tra cross-reference:

```text
character references valid
world/location references valid
screenplay revision pinned
asset provenance valid
review revision pinned
```

---

## Phase 9 gate

Production source:

```text
DEFAULT_CHARACTERS       = 0
DEFAULT_SCENES           = 0
DEFAULT_COMMENTS         = 0
DEFAULT_VERSIONS         = 0
fake generation timer    = 0
hardcoded media URL      = 0 runtime dependency
```

Và:

```text
Characters E2E            PASS
World E2E                 PASS
Storyboard E2E            PASS
Reviews E2E               PASS
Assets E2E                PASS
cross-domain integration  PASS
Web                       PASS
Desktop                   PASS
```

Verdict:

```text
FRONTEND_V2_PHASE_09_STORY_PRODUCTION_VERIFIED
```

---

# PHASE 10 — Production Cutover

Phase 10 chuyển từ **kịch bản đã lock** sang production thật.

Hiện `ProductionWorkspacePage` hardcode `projectId: "proj-alpha"` và luôn trả `new FakeProductionApiClient()`.

Đây là thứ Phase 10 bắt buộc loại khỏi runtime.

---

## 10.0 — Scope boundary

Phase này tập trung:

```text
Frontend/API production architecture
+
wiring tới production engine hiện có
```

Không biến Phase 10 thành một dự án viết lại Blender/render engine.

Engine tiếp tục nằm sau application ports.

Frontend chỉ biết:

```text
ProductionPlan
Shot
Job
Artifact
Receipt
```

---

## 10.1 — Episode-centric Production

Không giữ Production là một project shell độc lập.

Canonical:

```text
Project
 └── Episode
      └── Production
```

Route:

```text
/studio/episodes/:episodeId/production
```

Workspace:

```text
Production
├── Overview
├── Shots
├── Audio
├── Animation
├── Render
└── Delivery
```

---

## 10.2 — Production contract

```text
ProductionPlan
Shot
ShotRevision
AudioJob
AnimationJob
RenderJob
VideoJob
DeliveryArtifact
```

Production Plan phải pin:

```text
screenplay_revision_id
storyboard_revision_id
character_revision/reference
asset_revision/reference
```

Không sản xuất từ `"latest"` không xác định.

---

## 10.3 — APIs

```http
GET /api/v3/episodes/:episodeId/production

GET  /api/v3/episodes/:episodeId/shots
POST /api/v3/episodes/:episodeId/shots

GET   /api/v3/shots/:id
PATCH /api/v3/shots/:id
```

Jobs:

```text
production.createPlan

audio.submit
audio.cancel
audio.retry

animation.submit
animation.cancel
animation.retry

render.submit
render.cancel
render.retry

video.submit
video.cancel
video.retry
```

Job response:

```json
{
  "job_id": "...",
  "state": "QUEUED",
  "submitted_at": "...",
  "correlation_id": "..."
}
```

---

## 10.4 — Job state machine

Không để từng engine tự phát minh status.

Canonical:

```text
PENDING
QUEUED
RUNNING
SUCCEEDED
FAILED
CANCELLED
BLOCKED
```

Với failure:

```text
error_code
retryable
failure_stage
attempt
max_attempts
```

---

## 10.5 — Production UI

```text
features/production/
├── ProductionPage.tsx
├── ProductionOverview.tsx
├── ShotList.tsx
├── ShotInspector.tsx
├── AudioPanel.tsx
├── AnimationPanel.tsx
├── RenderPanel.tsx
├── DeliveryPanel.tsx
└── components/
    ├── JobProgress.tsx
    ├── JobFailure.tsx
    ├── RetryAction.tsx
    └── ArtifactPreview.tsx
```

Không còn:

```tsx
new FakeProductionApiClient()
```

trong production application.

`FakeProductionApiClient` được phép tồn tại tại:

```text
tests/
fixtures/
storybook/
```

cho đến Phase 16 cleanup.

---

## 10.6 — Realtime production jobs

Event types:

```text
production.started

shot.updated

audio.started
audio.completed
audio.failed

animation.started
animation.completed
animation.failed

render.started
render.progress
render.completed
render.failed

video.completed
```

Đặc biệt render lâu phải support:

```text
reconnect
resume
snapshot
sequence gap recovery
```

Không phụ thuộc vào page đang mở.

---

## 10.7 — Failure UX

Ví dụ render fail do VRAM:

```text
FAILED
RENDER_OUT_OF_MEMORY
retryable=false/true
```

UI phải hiển thị failure thật.

Không tự đổi thành success.

Nếu job retryable:

```text
Retry
```

Nếu cần human action:

```text
Blocked
→ reason
→ suggested action
```

---

## 10.8 — Artifact integration

Output của từng stage phải trở thành artifact/asset thật:

```text
TTS output
animation cache
scene render
shot render
final video
```

Không lưu URL tùy tiện trong component.

Frontend tham chiếu:

```text
artifact_id
asset_id
revision_id
```

---

## 10.9 — Production certification E2E

Tối thiểu phải chạy được:

```text
Open LOCKED Episode
       ↓
Open Production
       ↓
Create Production Plan
       ↓
Load Storyboard
       ↓
Create/verify Shots
       ↓
Submit at least one REAL production job
       ↓
Observe QUEUED
       ↓
RUNNING
       ↓
SUCCEEDED or truthful FAILED
       ↓
Artifact persisted
       ↓
Refresh application
       ↓
same job + artifact recovered
```

Quan trọng: **SUCCESS không phải điều kiện duy nhất để PASS**.

Ví dụ Blender/render engine không thể render do asset thật bị thiếu thì:

```text
BLOCKED / FAILED
+
truthful reason
+
persistent receipt
```

vẫn chứng minh frontend/API architecture hoạt động chính xác.

Fake-success mới là FAIL.

---

# Phase 10 gate

```text
FakeProductionApiClient runtime usage    = 0
hardcoded proj-alpha                     = 0
production local-only state authority    = 0
fake setTimeout jobs                     = 0
direct /api/v2 production call           = 0

Episode → Production context             PASS
real job receipt                         PASS
job realtime                             PASS
reconnect recovery                       PASS
failure UX                               PASS
artifact persistence                     PASS
Web                                      PASS
Desktop                                  PASS
```

Verdict:

```text
FRONTEND_V2_PHASE_10_PRODUCTION_VERIFIED
```

---

# Test matrix bắt buộc cho Phase 6–10

| Test                     | P6 | P7 | P8 | P9 | P10 |
| ------------------------ | -: | -: | -: | -: | --: |
| TypeScript               |  ✓ |  ✓ |  ✓ |  ✓ |   ✓ |
| ESLint architecture      |  ✓ |  ✓ |  ✓ |  ✓ |   ✓ |
| Backend unit             |  ✓ |  ✓ |  ✓ |  ✓ |   ✓ |
| Frontend unit            |  ✓ |  ✓ |  ✓ |  ✓ |   ✓ |
| OpenAPI validation       |  ✓ |  ✓ |  ✓ |  ✓ |   ✓ |
| Generated client compile |  ✓ |  ✓ |  ✓ |  ✓ |   ✓ |
| Contract tests           |  ✓ |  ✓ |  ✓ |  ✓ |   ✓ |
| Web build                |  ✓ |  ✓ |  ✓ |  ✓ |   ✓ |
| Desktop build            |  ✓ |  ✓ |  ✓ |  ✓ |   ✓ |
| Web E2E                  |  ✓ |  ✓ |  ✓ |  ✓ |   ✓ |
| Desktop smoke            |  ✓ |  ✓ |  ✓ |  ✓ |   ✓ |
| Realtime reconnect       |  ✓ |  — |  ✓ |  ✓ |   ✓ |
| Visual regression        |  ✓ |  ✓ |  ✓ |  ✓ |   ✓ |
| Persistence/reload       |  ✓ |  ✓ |  ✓ |  ✓ |   ✓ |

---

# Evidence protocol

Tôi đề xuất giữ cùng structure cho cả 5 phase:

```text
artifacts/frontend_restructure/
├── phase_06/
│   ├── baseline/
│   ├── contracts/
│   ├── tests/
│   ├── e2e/
│   ├── screenshots/
│   └── final/
│
├── phase_07/
├── phase_08/
├── phase_09/
└── phase_10/
```

Mỗi `final/` bắt buộc:

```text
final_verdict.json
phase_report.md
changed_files.json
api_contract_report.json
architecture_report.json
frontend_test_report.json
backend_test_report.json
web_build_report.json
desktop_build_report.json
e2e_report.json
mock_runtime_scan.json
legacy_api_scan.json
risk_register.md
```

Không được ghi `PASS` chỉ dựa vào số test.

`final_verdict.json` phải liệt kê riêng:

```text
tests_passed
contract_passed
architecture_passed
runtime_mock_free
legacy_api_free_for_scope
web_verified
desktop_verified
critical_e2e_verified
```

---

# Quy tắc implementation xuyên Phase 6–10

Các coding agent phải tuân thủ các invariant sau:

```text
Không tự sửa domain business logic ngoài scope.

Không đổi API contract mà không regenerate OpenAPI client.

Không direct fetch trong feature.

Không thêm mock runtime để "làm UI chạy".

Không fallback từ API failure sang fake data.

Không fake job bằng setTimeout.

Không copy handwritten contract sang frontend.

Không tạo Store riêng trong Page.

Không tự parse location.hash.

Không tạo idempotency key riêng tại từng page.

Không xóa V2 backend trước Phase 15.

Không xóa dead frontend trước Phase 16.

Không cho Web import source từ Desktop.

Không thay đổi visual direction đã chốt ở Phase 5
trừ khi cần accessibility/responsive correctness.
```

---

# Điểm checkpoint quan trọng nhất

Tôi sẽ đặt ba checkpoint lớn:

```text
PHASE 6 PASS
    ↓
Frontend infrastructure proven
    ↓
PHASE 7 + 8
    ↓
SCREENPLAY_VERTICAL_SLICE_VERIFIED
    ↓
PHASE 9
    ↓
STORY_PRODUCTION_DOMAIN_VERIFIED
    ↓
PHASE 10
    ↓
REAL_PRODUCTION_CUTOVER_VERIFIED
```

Trong đó **Phase 8 phải được xem là gate ưu tiên cao nhất**. Nếu flow:

```text
Project
→ Episode
→ Idea
→ Story
→ Screenplay
→ Review
→ Lock
```

chưa chạy ổn định bằng backend thật, **không nên đẩy mạnh Phase 9/10**, vì Characters, Storyboard, Assets và Production đều phụ thuộc screenplay/revision authority này.

Sau Phase 10, trạng thái mong muốn là: **toàn bộ chuỗi từ Project → screenplay đã lock → Storyboard/Character/World/Assets → Production đã chạy trên frontend architecture mới; runtime không còn phụ thuộc `DEFAULT_*`, `Math.random()`, `setTimeout()` giả generation hoặc `FakeProductionApiClient`.** Khi đó mới hợp lý đi tiếp Phase 11 Agent System và Phase 12 Model Infrastructure.
