# WINDAGENT STUDIO — ROADMAP 1

## Story Foundation & Short Screenplay Production

**Baseline commit:** `9a09375700db02a64315068f008b15e43ba5f42d`
**Target product:** WindAgent Studio
**Roadmap scope:** Refactor nền tảng + hoàn thiện pipeline Idea → Story → Short Screenplay
**Out of scope:** Hoàn thiện Blender/Unreal production pipeline, render episode hoàn chỉnh, final video.

---

# 1. Mục tiêu tổng thể

Roadmap 1 chuyển WindAgent từ:

```text
General-purpose AI Agent Framework
+
Video Production modules
+
Partially integrated Story modules
```

thành:

```text
WindAgent Studio
│
├── Runtime Kernel
│   ├── Orchestrator
│   ├── Worker
│   ├── Scheduler
│   ├── Storage
│   ├── Events / Outbox
│   ├── Providers
│   ├── Model Router
│   ├── Tools
│   ├── Memory
│   └── Verification
│
├── Studio Domain
│   ├── SeriesProject
│   ├── Episode
│   ├── ProductionRevision
│   └── ApprovalPolicy
│
└── Story Domain
    ├── Idea
    ├── Story Bible
    ├── World Bible
    ├── Character Canon
    ├── Beat Sheet
    ├── Episode Outline
    ├── Screenplay
    ├── Review
    └── Lock
```

Roadmap kết thúc khi hệ thống thực hiện được pipeline thật:

```text
User Prompt
   ↓
SeriesProject
   ↓
Episode
   ↓
Idea Generation
   ↓
Idea Selection
   ↓
Story Development
   ↓
Story Bible / World Context
   ↓
Beat Sheet
   ↓
Episode Outline
   ↓
Short Screenplay Draft
   ↓
Automated Review
   ↓
Revision
   ↓
Optional Human Approval
   ↓
LOCKED SCREENPLAY
   ↓
READY_FOR_PRODUCTION
```

Pipeline trên phải chạy thông qua:

```text
API V3
  ↓
OrchestratorService
  ↓
Durable Worker
  ↓
Story Services
  ↓
Model Router / Provider
  ↓
Persistence
  ↓
Review / Verification
```

Không được chứng nhận bằng cách gọi trực tiếp helper hoặc test orchestrator nội bộ.

---

# 2. Các nguyên tắc kiến trúc bắt buộc

## 2.1 Một orchestration authority duy nhất

Canonical authority:

```text
OrchestratorService
```

Không duy trì đồng thời:

```text
Generic Workflow Engine
Production Workflow Engine
Story Workflow Engine
```

như ba authority độc lập.

Target:

```text
                    OrchestratorService
                           │
             ┌─────────────┼─────────────┐
             │             │             │
          Story DAG     Asset DAG    Production DAG
             │
        Durable Worker
             │
     Execution Runtime
```

`ProductionWorkflowEngine` hiện tại phải được đưa vào deprecation path.

Roadmap 1 chỉ bắt buộc Story DAG được cutover hoàn toàn.

Production DAG sẽ hoàn tất migration trong Roadmap 2.

Worker hiện đã có generic `ExecutionRuntimeRegistry`, trong khi production runtime còn một đường orchestration riêng, nên việc hội tụ authority là một trong các refactor nền móng.

---

# 3. Canonical Project Model

Target hierarchy:

```text
SeriesProject
│
├── Series Bible
├── World Bible
├── Character Canon
├── Visual / Narrative Style
├── Shared Asset References
│
├── Episode 001
│   ├── Idea
│   ├── Story Development
│   ├── ProductionRevision 1
│   ├── ProductionRevision 2
│   └── Locked Screenplay
│
├── Episode 002
│
└── Episode N
```

Không tạo một Project aggregate mới song song với model hiện có.

Repo hiện đã có `VideoProject` và immutable `ProductionRevision`, bao gồm parent revision, content hash, lock semantics và invalidation intent. Các model này phải được **migrate và nâng cấp**, không rewrite.

---

# 4. Phạm vi Roadmap 1

## IN SCOPE

* sửa baseline/evidence;
* sửa architecture boundaries cần thiết;
* hội tụ orchestration;
* chuyển WindAgent thành Studio-first architecture;
* `SeriesProject`;
* `Episode`;
* revision model;
* Story domain;
* Idea generation;
* Story Bible;
* World Bible;
* Character Canon;
* Beat Sheet;
* Episode Outline;
* Screenplay generation;
* screenplay validation;
* screenplay review;
* revision loop;
* human approval;
* configurable approval policy;
* screenplay locking;
* `/api/v3/studio`;
* Story frontend;
* Desktop certification;
* real model integration;
* deterministic testing;
* vertical slice Idea → Locked Screenplay.

## OUT OF SCOPE

Roadmap 1 không cố hoàn thiện:

* automatic 3D asset acquisition;
* full asset generation;
* Blender GPU rendering;
* Unreal Engine runtime;
* animation;
* rigging production workflow;
* lipsync production;
* full TTS pipeline;
* music/SFX production;
* shot rendering;
* post-production;
* 5–20 minute episode render;
* final MP4 certification.

Những module đã tồn tại phải được **preserve**, không delete hoặc rewrite.

---

# 5. Target package layout

Không nhất thiết thực hiện một lần. Đây là trạng thái cuối mong muốn sau Roadmap 1.

```text
core/
└── windagent_core/
    └── domain/
        ├── studio/
        │   ├── series_project.py
        │   ├── episode.py
        │   ├── revision.py
        │   ├── approval_policy.py
        │   ├── states.py
        │   ├── events.py
        │   └── errors.py
        │
        └── story/
            ├── idea.py
            ├── story_bible.py
            ├── world_bible.py
            ├── character_canon.py
            ├── beat_sheet.py
            ├── episode_outline.py
            ├── screenplay.py
            ├── screenplay_review.py
            ├── screenplay_lock.py
            ├── continuity.py
            ├── states.py
            └── events.py


intelligence/
└── windagent_intelligence/
    └── story/
        ├── ideation/
        ├── development/
        ├── outline/
        ├── screenplay/
        ├── review/
        └── prompts/


orchestration/
└── windagent_orchestration/
    └── studio/
        ├── story_dag.py
        ├── story_handlers.py
        ├── episode_execution.py
        └── transition_policy.py


apps/api/
└── windagent_api/
    └── routers/
        └── v3/
            └── studio/
                ├── projects.py
                ├── episodes.py
                ├── ideas.py
                ├── story.py
                ├── screenplay.py
                ├── reviews.py
                └── runs.py


frontend/packages/
├── studio-contracts/
├── studio-client/
├── studio-state/
├── story-ui/
└── studio-shell/
```

---

# 6. Execution Waves

```text
WAVE 0
Baseline Truth
      │
      ▼
WAVE 1
Architecture Foundation
      │
      ▼
WAVE 2
Studio Domain
      │
      ├──────────────┐
      ▼              ▼
WAVE 3A          WAVE 3B
Story Domain     Story Intelligence
      └──────┬───────┘
             ▼
WAVE 4
Story Runtime
             │
             ▼
WAVE 5
Review + Lock
             │
      ┌──────┴──────┐
      ▼             ▼
WAVE 6A         WAVE 6B
API V3          Frontend
      └──────┬──────┘
             ▼
WAVE 7
Vertical Slice
             │
             ▼
WAVE 8
Certification
```

---

# PHASE S0 — CURRENT TRUTH BASELINE

## Mục tiêu

Xác định trạng thái thật của commit:

```text
9a09375700db02a64315068f008b15e43ba5f42d
```

trước khi sửa bất cứ thứ gì.

---

## S0.1 Freeze baseline

Ghi lại:

* commit SHA;
* branch;
* Python version;
* Node version;
* OS;
* database backend;
* Blender detection;
* Unreal detection nếu có;
* git status;
* tracked/untracked changes.

Artifact:

```text
artifacts/studio_refactor/roadmap_01/phase_s0/
    baseline_environment.json
    baseline_git_state.json
```

---

## S0.2 Run live architecture validation

Không dùng artifact PASS cũ làm source of truth.

Chạy live:

```text
architecture checker
dependency checker
version checker
import checker
scaffold checker
artifact schema checker
```

Mọi FAIL phải được ghi lại.

Không auto-fix.

---

## S0.3 Full regression baseline

Chạy:

```text
Python tests
Frontend tests
Desktop tests
CLI tests
API tests
Storage tests
Architecture tests
```

Các test production/Blender không chạy được vì environment phải được:

```text
SKIPPED_WITH_REASON
```

không được biến thành PASS.

---

## S0.4 Evidence drift report

So sánh:

```text
committed evidence
vs
live execution
```

Tạo:

```text
evidence_drift_report.json
```

Phân loại:

```text
CURRENT
STALE
MISSING
INVALID
ENVIRONMENT_BOUND
```

---

## Gate

```text
WIND_STUDIO_S0_CURRENT_TRUTH_CAPTURED
```

Gate này **có thể PASS ngay cả khi tests/checkers FAIL**, miễn là trạng thái thật đã được capture chính xác.

---

# PHASE S1 — EVIDENCE & VERSION AUTHORITY REPAIR

## Mục tiêu

Không để refactor dựa trên evidence sai.

---

## S1.1 Single version authority

Loại bỏ version literals rải rác.

Canonical source ví dụ:

```text
windagent_version
```

API, CLI, Worker, Desktop phải derive từ authority này.

---

## S1.2 Evidence storage policy

Git chỉ lưu:

```text
manifest
summary
verdict
schema
small deterministic reports
```

Không commit:

```text
render frames
MP4
EXR
large logs
Blender runtime state
large receipts
temporary workspaces
```

Raw runtime evidence → CI artifact storage.

Commit `9a093...` đã xóa nhiều runtime Blender receipts, cho thấy cơ chế cũ không phù hợp để duy trì lâu dài.

---

## S1.3 Fresh evidence generation

Mỗi CI run phải regenerate:

```text
architecture_report
version_report
test_matrix
artifact_manifest
runtime_smoke_report
```

Artifact phải chứa:

```text
source_commit_sha
generated_at
tool_version
environment
```

---

## Gate

```text
WIND_STUDIO_S1_EVIDENCE_AUTHORITY_VERIFIED
```

Required:

```text
no stale PASS
version checker PASS
evidence schema PASS
```

---

# PHASE S2 — ORCHESTRATION CONVERGENCE FOUNDATION

## Mục tiêu

Chuẩn bị một orchestration authority duy nhất.

---

## S2.1 Inventory orchestration authorities

Lập graph:

```text
OrchestratorService
DurablePlanScheduler
WorkflowEngine
ProductionWorkflowEngine
ExecutionRuntimeRegistry
ProductionStepExecutor
ProductionEngineExecutor
Worker task loop
```

Đánh dấu:

```text
AUTHORITY
EXECUTOR
ADAPTER
LEGACY
```

---

## S2.2 Canonical responsibility

Sau refactor:

### OrchestratorService

chịu trách nhiệm:

* DAG;
* dependencies;
* state transitions;
* retries policy;
* pause/resume;
* approval wait states.

### Worker

chịu trách nhiệm:

* durable dequeue;
* lease;
* fencing;
* dispatch;
* heartbeat;
* finalize;
* recovery.

### Execution Runtime

chịu trách nhiệm:

* execute one task;
* model/tool/provider invocation.

Không service nào khác được tạo DAG độc lập.

---

## S2.3 ProductionWorkflowEngine deprecation contract

Chưa xóa code production.

Thêm marker:

```text
DEPRECATED_ORCHESTRATION_AUTHORITY
```

Cấm feature mới depend trực tiếp lên nó.

Roadmap 2 mới hoàn tất production migration.

---

## S2.4 Story execution namespace

Định nghĩa task types:

```text
studio.story.idea.generate
studio.story.idea.evaluate
studio.story.bible.generate
studio.story.beats.generate
studio.story.outline.generate
studio.story.screenplay.generate
studio.story.screenplay.review
studio.story.screenplay.revise
studio.story.screenplay.lock
```

---

## Gate

```text
WIND_STUDIO_S2_SINGLE_ORCHESTRATION_AUTHORITY_DEFINED
```

Architecture test phải đảm bảo Story code không import:

```text
ProductionWorkflowEngine
legacy WorkflowEngine
```

---

# PHASE S3 — STUDIO PROJECT DOMAIN

## Mục tiêu

Biến `VideoProject` thành project model phù hợp sản xuất series.

---

## S3.1 Introduce SeriesProject

Canonical:

```text
SeriesProject
```

Fields tối thiểu:

```text
series_id
title
description
status

target_audience
language
genre
tone

created_at
updated_at

current_bible_revision
approval_policy

metadata
```

---

## S3.2 Compatibility migration

Current:

```text
VideoProject
```

Target:

```text
SeriesProject
```

Trong migration window:

```python
VideoProject -> deprecated compatibility facade
```

Không tạo database duplicate.

---

## S3.3 Episode aggregate

Tạo:

```text
Episode
```

Fields:

```text
episode_id
series_id

title
logline

target_duration
target_audience

state

active_revision_id

created_at
updated_at
```

---

## S3.4 Episode state machine

Canonical states:

```text
DRAFT
↓
IDEATION
↓
IDEA_SELECTED
↓
STORY_DEVELOPMENT
↓
OUTLINE_READY
↓
SCREENPLAY_DRAFT
↓
SCREENPLAY_REVIEW
↓
SCREENPLAY_APPROVAL
↓
SCREENPLAY_LOCKED
↓
READY_FOR_PRODUCTION
```

Không được nhảy state tùy ý.

---

## S3.5 Upgrade ProductionRevision

`ProductionRevision` phải gắn với:

```text
series_id
episode_id
revision_id
parent_revision_id
content_hash
created_by
created_at
locked
invalidation_intent
```

Current immutable revision mechanism phải được reuse.

---

## S3.6 ApprovalPolicy

Per-Series hoặc per-Episode:

```text
AUTO
HUMAN_REQUIRED
QUALITY_GATE_ONLY
```

Cho các checkpoint:

```text
IDEA
STORY_BIBLE
OUTLINE
SCREENPLAY
```

Ví dụ:

```json
{
  "idea": "AUTO",
  "story_bible": "AUTO",
  "outline": "HUMAN_REQUIRED",
  "screenplay": "HUMAN_REQUIRED"
}
```

---

## Gate

```text
WIND_STUDIO_S3_STUDIO_DOMAIN_CANONICAL
```

Tests bắt buộc:

* create SeriesProject;
* create Episode;
* derive revision;
* cannot mutate locked revision;
* invalid transition rejected;
* approval policy respected.

---

# PHASE S4 — STORY DOMAIN EXTRACTION

## Mục tiêu

Tách creative-story logic khỏi `video_production`.

---

## S4.1 Inventory existing story logic

Phân loại:

```text
KEEP
MOVE
MERGE
DEPRECATE
DELETE
```

Các nhóm cần rà:

```text
screenplay
ideation
character
narrator
brief expander
outline
social research
reviewer
summarizer
reporter
```

---

## S4.2 Compatibility-first move

Không bulk move toàn bộ code trong một commit.

Pattern:

```text
new canonical module
       ↑
compatibility facade
       ↑
old imports
```

Sau khi imports cũ = 0 mới remove facade.

---

## S4.3 Story entities

Tạo canonical entities.

### IdeaCandidate

```text
idea_id
title
premise
logline
theme
target_audience
genre
estimated_duration
characters
setting
hook
scores
```

### StoryBible

```text
premise
theme
core_conflict
tone
story_rules
character_arcs
episode_constraints
```

### WorldBible

```text
world_summary
locations
rules
culture
technology_or_magic
continuity_constraints
```

### CharacterCanon

```text
character_id
name
role
personality
motivation
fear
strength
weakness
speech_style
relationships
visual_identity_ref
continuity_rules
```

### BeatSheet

```text
beats[]
```

Mỗi beat:

```text
purpose
conflict
turn
character_change
estimated_duration
```

### EpisodeOutline

```text
acts
sequences
scenes
story_progression
```

---

## Gate

```text
WIND_STUDIO_S4_STORY_DOMAIN_EXTRACTED
```

Condition:

```text
story canonical modules do not depend on Blender
story canonical modules do not depend on production engine
```

---

# PHASE S5 — STORY INTELLIGENCE PIPELINE

## Mục tiêu

Biến các module creative hiện có thành một pipeline thực sự.

---

# S5.1 Model roles

Không hardcode provider.

Canonical roles:

```text
IDEATION_MODEL
STORY_ARCHITECT_MODEL
SCREENPLAY_MODEL
REVIEW_MODEL
REVISION_MODEL
```

Model Router chọn provider/model.

Domain không biết:

```text
Gemini
OpenRouter
Ollama
DeepSeek
Qwen
```

---

# S5.2 Structured generation contract

Mọi generation step phải trả structured output.

Không chấp nhận raw prose rồi parse tùy tiện nếu contract quan trọng.

Ví dụ:

```text
IdeaCandidate[]
StoryBible
BeatSheet
EpisodeOutline
ScreenplayDraft
ReviewReport
```

Use:

```text
schema validation
retry on schema error
```

---

# S5.3 Prompt versioning

Prompt không nằm rải trong source.

Target:

```text
intelligence/story/prompts/
    idea/
    bible/
    outline/
    screenplay/
    review/
```

Mỗi prompt có:

```text
prompt_id
version
role
input_schema
output_schema
```

---

# PHASE S6 — IDEA PIPELINE

## Mục tiêu

Tạo được một idea đủ tốt và ổn định trước khi viết screenplay.

---

## S6.1 Input Creative Brief

Minimum:

```text
target audience
genre
episode duration
language
theme optional
characters optional
setting optional
constraints optional
```

---

## S6.2 Idea generation

Generate:

```text
3–5 IdeaCandidate
```

Không generate một idea duy nhất.

---

## S6.3 Idea evaluation

Score tối thiểu:

```text
originality
clarity
emotional potential
audience fit
character potential
production feasibility
episode-duration fit
```

---

## S6.4 Candidate selection

Có hai modes:

```text
AUTO_SELECT
HUMAN_SELECT
```

AUTO:

```text
quality score + policy
```

HUMAN:

API/UI hiển thị candidates.

---

## S6.5 Idea lock

Selected idea tạo immutable:

```text
SelectedIdea
```

và revision.

---

## Gate

```text
WIND_STUDIO_S6_IDEA_PIPELINE_VERIFIED
```

Acceptance:

Từ một brief phải tạo:

```text
>=3 valid ideas
```

và chọn được:

```text
1 canonical idea
```

không sửa database trực tiếp.

---

# PHASE S7 — STORY DEVELOPMENT

## Mục tiêu

Chuyển idea thành cấu trúc câu chuyện đủ chắc trước screenplay.

---

## S7.1 Story Bible generation

Input:

```text
SelectedIdea
Series Bible
existing character canon
```

Output:

```text
StoryBible
```

---

## S7.2 World Bible

Nếu Series đã có WorldBible:

```text
reuse
```

Nếu chưa có:

```text
generate minimum viable WorldBible
```

Không regenerate WorldBible mỗi episode nếu không cần.

---

## S7.3 Character handling

Rules:

```text
existing recurring character
→ use CharacterCanon

new character
→ propose → approve → add canon
```

Screenplay validator không được hardcode character IDs.

---

## S7.4 Beat Sheet generation

Target short screenplay:

Ví dụ 3–8 phút:

```text
5–12 beats
```

Không hardcode exact count.

Quality constraints:

```text
clear setup
conflict
progression
turn
resolution
```

---

## S7.5 Episode Outline

BeatSheet → scenes.

Mỗi scene:

```text
scene_id
location
time
characters
objective
conflict
turn
estimated_duration
story_value
```

---

## Gate

```text
WIND_STUDIO_S7_STORY_DEVELOPMENT_VERIFIED
```

Phải prove:

```text
Idea
→ StoryBible
→ BeatSheet
→ EpisodeOutline
```

và mọi artifact cùng revision chain.

---

# PHASE S8 — SCREENPLAY GENERATION

## Mục tiêu

Sinh được screenplay ngắn thực sự có thể đọc và đánh giá.

---

## S8.1 Screenplay contract

Một scene:

```text
Scene Heading
Action
Character
Dialogue
Parenthetical optional
Transition optional
```

Canonical structured representation phải tồn tại bên cạnh formatted script.

---

## S8.2 Screenplay generation

Input:

```text
Series Bible
World Bible
Character Canon
Story Bible
Beat Sheet
Episode Outline
target duration
```

Không cho model tự bỏ qua upstream artifacts.

---

## S8.3 Duration estimator

Ước lượng:

```text
dialogue duration
action duration
scene duration
total runtime
```

Tolerance ban đầu:

```text
±20%
```

---

## S8.4 Continuity validation

Validate:

```text
character existence
location existence
character consistency
world rules
timeline
props
scene order
unresolved references
```

---

## S8.5 Production feasibility check — basic

Roadmap 1 chưa production video nhưng screenplay phải tránh output bất khả thi.

Basic flags:

```text
excessive unique locations
excessive unique characters
extreme crowd requirement
impossible scene duration
ambiguous physical action
missing setting information
```

Không block creative choice tuyệt đối.

Chỉ report risk.

---

## Gate

```text
WIND_STUDIO_S8_SHORT_SCREENPLAY_GENERATED
```

Acceptance:

```text
structured screenplay valid
formatted screenplay valid
runtime estimate available
all characters resolved
all scenes linked to outline
```

---

# PHASE S9 — STORY REVIEW & REVISION LOOP

## Mục tiêu

Không coi model-generated screenplay là kết quả cuối ngay lập tức.

---

## S9.1 Minimum Review Framework

Không cần làm 16-phase eval lớn ngay.

V1 reviewer phải đánh giá:

```text
premise coherence
plot coherence
character consistency
continuity
pacing
dialogue quality
scene purpose
emotional progression
target audience suitability
production feasibility
```

---

## S9.2 ReviewReport

Output:

```text
overall_score
dimension_scores
blocking_findings[]
warnings[]
suggestions[]
revision_required
```

---

## S9.3 Severity

```text
BLOCKING
MAJOR
MINOR
SUGGESTION
```

---

## S9.4 Automatic revision

Nếu:

```text
BLOCKING > 0
```

hoặc score dưới threshold:

```text
ScreenplayDraft
→ Review
→ Revision
→ Review
```

Max iterations configurable.

Ví dụ default:

```text
3
```

Không infinite retry.

---

## S9.5 Revision diff

Mỗi revision phải lưu:

```text
parent_revision
changed_scenes
change_reason
review_findings_addressed
```

---

## Gate

```text
WIND_STUDIO_S9_SCREENPLAY_REVIEW_LOOP_VERIFIED
```

---

# PHASE S10 — HUMAN APPROVAL & SCREENPLAY LOCK

## Mục tiêu

Biến screenplay thành canonical production input.

---

## S10.1 Approval behavior

Theo `ApprovalPolicy`.

Ví dụ:

```text
AUTO
→ lock nếu quality gate PASS

HUMAN_REQUIRED
→ WAITING_FOR_APPROVAL

QUALITY_GATE_ONLY
→ auto nếu score đạt threshold
```

---

## S10.2 Human commands

Support:

```text
approve
reject
request_revision
edit
unlock-derived-revision
```

Không sửa locked screenplay trực tiếp.

---

## S10.3 Screenplay lock

Lock tạo:

```text
LockedScreenplayReceipt
```

Fields:

```text
series_id
episode_id
revision_id
screenplay_hash
approved_by
approved_at
review_report_id
```

---

## S10.4 Episode transition

Sau lock:

```text
SCREENPLAY_LOCKED
        ↓
READY_FOR_PRODUCTION
```

Đây là boundary chính giữa:

```text
Roadmap 1
```

và:

```text
Roadmap 2
```

---

## Gate

```text
WIND_STUDIO_S10_LOCKED_SCREENPLAY_CANONICAL
```

---

# PHASE S11 — API V3 STUDIO

## Mục tiêu

Không tiếp tục mở rộng `/api/v2/video-production`.

Repo đã có Production Workspace API V2 khá đầy đủ với project lookup, workspace snapshot, optimistic concurrency và idempotent commands. Logic tốt phải được reuse thay vì bỏ.

---

## Base

```text
/api/v3/studio
```

---

## S11.1 Projects

```text
POST /series
GET  /series
GET  /series/{series_id}
PATCH /series/{series_id}
```

---

## S11.2 Episodes

```text
POST /series/{series_id}/episodes

GET /episodes/{episode_id}
GET /episodes/{episode_id}/state
GET /episodes/{episode_id}/revisions
```

---

## S11.3 Idea

```text
POST /episodes/{episode_id}/idea/generate
GET  /episodes/{episode_id}/ideas
POST /episodes/{episode_id}/ideas/{idea_id}/select
```

---

## S11.4 Story

```text
POST /episodes/{episode_id}/story/develop

GET /episodes/{episode_id}/story-bible
GET /episodes/{episode_id}/beat-sheet
GET /episodes/{episode_id}/outline
```

---

## S11.5 Screenplay

```text
POST /episodes/{episode_id}/screenplay/generate

GET /episodes/{episode_id}/screenplay

POST /episodes/{episode_id}/screenplay/review
POST /episodes/{episode_id}/screenplay/revise
POST /episodes/{episode_id}/screenplay/approve
POST /episodes/{episode_id}/screenplay/reject
POST /episodes/{episode_id}/screenplay/lock
```

---

## S11.6 Async run API

Long-running operations không giữ HTTP request mở.

```text
POST
→ run_id
```

Poll/stream:

```text
GET /runs/{run_id}
GET /runs/{run_id}/events
```

Later:

```text
SSE/WebSocket
```

---

## S11.7 Concurrency

Reuse existing:

```text
revision_id
idempotency key
optimistic concurrency
```

---

## V2 Sunset

V2:

```text
/api/v2/video-production
```

status:

```text
DEPRECATED
```

Roadmap 1 chưa bắt buộc delete.

---

## Gate

```text
WIND_STUDIO_S11_API_V3_STORY_VERIFIED
```

---

# PHASE S12 — STORY FRONTEND

## Product surfaces

Roadmap 1 frontend chỉ cần:

```text
Studio Home
Series
Episode
Story
Screenplay
```

Không cần Production UI hoàn chỉnh.

---

## S12.1 Studio Home

Hiển thị:

```text
series
episodes
status
latest revision
```

---

## S12.2 Episode Story Workspace

Tabs:

```text
IDEA
STORY
OUTLINE
SCREENPLAY
REVIEW
```

---

## S12.3 Idea UI

Hiển thị candidate cards:

```text
title
logline
premise
scores
select
regenerate
```

---

## S12.4 Story UI

Cho xem/edit:

```text
Story Bible
Character Canon
Beat Sheet
Outline
```

---

## S12.5 Screenplay UI

Editor tối thiểu:

```text
scene list
script content
review findings
revision
approve
lock
```

---

## S12.6 Remove fake runtime from production path

Frontend hiện có cả `HttpProductionApiClient` và `FakeProductionApiClient`; real client vẫn hardcode một số behavior như `vp_001` và synthesized revision.

Production build:

```text
Fake client forbidden
```

Fake client chỉ được import từ:

```text
tests/
stories/
fixtures/
```

---

## S12.7 No hardcoded project

Cấm:

```text
proj-alpha
vp_001
```

trong runtime UI.

---

## Desktop certification

Desktop/Tauri:

```text
REQUIRED
```

Web:

```text
BUILD + TEST REQUIRED
FULL PRODUCT CERTIFICATION NOT REQUIRED
```

---

## Gate

```text
WIND_STUDIO_S12_STORY_UI_LIVE
```

---

# PHASE S13 — STORY VERTICAL SLICE

Đây là phase quan trọng nhất Roadmap 1.

---

# Test Case A — Basic children's animation story

Input ví dụ:

```text
Một chú thỏ nhỏ làm mất chiếc diều yêu thích
và cùng người bạn sóc đi tìm nó.
Đối tượng: trẻ em 5–8 tuổi.
Thời lượng mục tiêu: 3–5 phút.
```

Không hardcode output.

---

## Required runtime path

```text
Desktop/API
      ↓
POST /api/v3/studio/series
      ↓
Create Episode
      ↓
OrchestratorService
      ↓
Idea Generation Task
      ↓
Worker
      ↓
Model Router
      ↓
Idea Candidates
      ↓
Selection
      ↓
Story Development DAG
      ↓
Story Bible
      ↓
Beat Sheet
      ↓
Outline
      ↓
Screenplay Generation
      ↓
Review
      ↓
Revision if needed
      ↓
Approval Policy
      ↓
Lock
      ↓
READY_FOR_PRODUCTION
```

---

## Không được phép

Vertical slice không được:

```text
call StoryWriter directly from test
call helper orchestrator directly
insert DB rows manually
use FakeProductionApiClient
use hardcoded screenplay
skip worker
skip persistence
```

---

## Required artifacts

```text
series_project.json
episode.json
selected_idea.json
story_bible.json
world_bible.json
character_canon.json
beat_sheet.json
episode_outline.json
screenplay_draft.json
review_report.json
final_screenplay.json
screenplay_lock_receipt.json
run_manifest.json
```

---

## Gate

```text
WIND_STUDIO_S13_REAL_STORY_VERTICAL_SLICE_PASS
```

---

# PHASE S14 — FAILURE & RECOVERY TESTING

## Test scenarios

### Provider timeout

Expected:

```text
retry
then deterministic failure state
```

### Invalid model JSON

Expected:

```text
schema rejection
retry
```

### Worker crash

Expected:

```text
lease recovery
resume/re-run safely
```

### Duplicate request

Expected:

```text
idempotent
```

### Stale revision

Expected:

```text
409 / conflict
```

### Locked screenplay mutation

Expected:

```text
reject
```

### Human approval timeout

Expected:

```text
WAITING_FOR_APPROVAL
```

Không fail job.

---

## Gate

```text
WIND_STUDIO_S14_STORY_RUNTIME_RESILIENT
```

---

# PHASE S15 — ROADMAP 1 FINAL CERTIFICATION

## Full test matrix

Required:

```text
Python full suite
Frontend tests
Desktop tests
API V3 contract tests
Story domain tests
Story DAG tests
Worker recovery tests
Provider adapter contract tests
Architecture checker
Version checker
Artifact validator
```

---

# Final certification requirements

## Architecture

```text
PASS
```

Story domain không depend:

```text
Blender
Unreal
filesystem adapters
database concrete implementation
FastAPI
React
```

---

## Runtime

Idea → Locked Screenplay chạy qua real:

```text
API
OrchestratorService
Worker
Provider
Storage
```

---

## Frontend

Không:

```text
Fake runtime client
hardcoded project
mock success fallback
```

trong production build.

---

## Story

Một short episode phải có:

```text
Idea
Story Bible
Character Canon
Beat Sheet
Episode Outline
Screenplay
Review
Locked Screenplay
```

---

## Revision

Locked screenplay:

```text
immutable
hash verified
revision traceable
```

---

## Evidence

Fresh evidence phải cùng commit SHA.

---

# FINAL VERDICT

Chỉ được công bố:

```text
WIND_STUDIO_ROADMAP_1_STORY_FOUNDATION_CERTIFIED
```

khi toàn bộ các điều kiện trên PASS.

---

# 7. Những phase có thể chạy song song

Sau S3:

```text
                    S3 Studio Domain
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
       S4 Story Domain         S5 Story Intelligence
             │                         │
             └────────────┬────────────┘
                          ▼
                       S6 Idea
```

Sau khi contract Story ổn định:

```text
S7 Story Development
        │
        ├───────────────┐
        ▼               ▼
   S8 Screenplay      S11 API skeleton
        │               │
        ▼               ▼
   S9 Review          S12 UI skeleton
```

Sau S10 + S11 + S12:

```text
S13 Vertical Slice
```

---

# 8. Critical Path

Critical path đề xuất:

```text
S0 Truth
 ↓
S1 Evidence
 ↓
S2 Orchestration
 ↓
S3 Studio Domain
 ↓
S4 Story Domain
 ↓
S6 Idea
 ↓
S7 Story Development
 ↓
S8 Screenplay
 ↓
S9 Review
 ↓
S10 Lock
 ↓
S11 API
 ↓
S12 UI
 ↓
S13 Vertical Slice
 ↓
S14 Recovery
 ↓
S15 Certification
```

---

# 9. Migration rules

Trong toàn Roadmap 1 áp dụng:

## Rule 1

```text
MOVE > REWRITE
```

## Rule 2

Module đang hoạt động phải có compatibility facade trước khi đổi import path.

## Rule 3

Không delete code chỉ vì "có vẻ không dùng".

Cần chứng minh:

```text
0 runtime caller
0 API caller
0 frontend caller
0 test dependency
0 migration dependency
```

## Rule 4

Không cleanup generic runtime trước khi Story runtime chạy thành công.

## Rule 5

Không mở rộng Blender/Unreal feature trong Roadmap 1 trừ thay đổi bắt buộc để giữ architecture/build/test.

## Rule 6

Không sửa CI ngoài scope chỉ để làm gate xanh.

Root cause phải được phân loại trước.

---

# 10. Phần VP3D trong Roadmap 1

Code hiện có:

```text
Blender adapter
ProductionEnginePort
Production Engine Executor
Asset pipeline
Director
Animation
Camera
Lighting
Audio
Review
Retry
```

được đặt vào trạng thái:

```text
PRESERVE
ISOLATE
REGRESSION TEST
```

Không đặt trạng thái:

```text
DELETE
REWRITE
EXPAND
```

Roadmap 2 mới tiếp tục.

---

# 11. Blender + Unreal architecture requirement

Mặc dù chưa triển khai sản xuất video trong Roadmap 1, architecture phải giữ:

```text
ProductionEnginePort
        │
        ├── BlenderEngineAdapter
        └── UnrealEngineAdapter
```

Không để Story domain import engine.

`RuntimeCapabilityProfile` được định nghĩa tối thiểu:

```text
BLENDER_AVAILABLE
UNREAL_AVAILABLE
FFMPEG_AVAILABLE
GPU_AVAILABLE
TTS_AVAILABLE
```

Roadmap 1 chỉ cần capability discovery foundation.

Roadmap 2 sẽ biến Blender + Unreal thành production-ready adapters.

---

# 12. Definition of Done cho Roadmap 1

Người dùng phải có thể:

1. mở WindAgent Studio;
2. tạo một Series;
3. tạo Episode;
4. nhập creative brief;
5. yêu cầu AI sinh nhiều idea;
6. chọn hoặc để AI chọn idea;
7. tạo Story Bible;
8. tạo Beat Sheet;
9. tạo Outline;
10. sinh screenplay ngắn;
11. xem automated review;
12. sửa hoặc cho AI revise;
13. approve;
14. lock screenplay;
15. nhìn thấy Episode:

```text
READY_FOR_PRODUCTION
```

Và toàn bộ quá trình phải:

```text
durable
revisioned
recoverable
auditable
provider-independent
UI-accessible
```

---

# 13. Handoff contract sang Roadmap 2

Roadmap 1 không tạo video.

Nó phải bàn giao cho Roadmap 2 một artifact ổn định:

```text
LockedScreenplayPackage
```

Bao gồm:

```text
series_id
episode_id
revision_id

series_bible_ref
world_bible_ref
character_canon_ref

selected_idea_ref
story_bible_ref
beat_sheet_ref
outline_ref

screenplay_ref
screenplay_hash

review_report_ref
approval_receipt_ref

target_duration
target_audience
language

production_constraints
```

Roadmap 2 bắt đầu tại:

```text
LockedScreenplayPackage
          ↓
Scene Breakdown
          ↓
Shot Planning
          ↓
Asset Requirements
          ↓
Director
          ↓
Audio
          ↓
Blender / Unreal
          ↓
Render
          ↓
Final Video
```

Roadmap 1 tuyệt đối không cần giả vờ hoàn thiện các bước này.

---

# 14. Success Criterion

Thành công của Roadmap 1 không phải:

```text
"We have lots of story classes."
```

cũng không phải:

```text
"All unit tests pass."
```

mà là:

```text
REAL USER INPUT
      ↓
REAL STUDIO API
      ↓
REAL ORCHESTRATOR
      ↓
REAL WORKER
      ↓
REAL MODEL
      ↓
REAL STORY ARTIFACTS
      ↓
REAL REVIEW
      ↓
REAL REVISION
      ↓
LOCKED SCREENPLAY
```

với trạng thái cuối:

```text
EPISODE_READY_FOR_PRODUCTION
```

và verdict:

```text
WIND_STUDIO_ROADMAP_1_STORY_FOUNDATION_CERTIFIED
```
