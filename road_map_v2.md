# ROADMAP II — WindAgent Production Frontend

## Script Workspace + Universal Asset Manager

## 0. Các quyết định kiến trúc đã khóa

```yaml
frontend_strategy:
  choice: C
  architecture: shared_production_frontend_package
  consumers:
    - apps/desktop
    - apps/web

screenplay_editor:
  choice: C
  mode: hybrid
  editors:
    - structured_editor
    - screenplay_text_editor

locked_screenplay_policy:
  choice: B
  policy: immutable_locked_revision
  editing_behavior: create_new_draft_revision

asset_manager_scope:
  choice: B
  scope: universal_production_resource_library
```

Kiến trúc mục tiêu:

```text
                     WindAgent Production Domain
                                │
                                ▼
                     Production API V2
                                │
                    ┌───────────┴───────────┐
                    │                       │
                 Commands                Queries
                    │                       │
                    └───────────┬───────────┘
                                │
                         Event Stream
                                │
                                ▼
             packages/production-ui
        ┌─────────────────────────────────┐
        │ Production Domain TS contracts  │
        │ API clients                     │
        │ Event projection                │
        │ State                           │
        │ Script Workspace                │
        │ Asset Manager                   │
        │ Shared Components               │
        └───────────────┬─────────────────┘
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
       apps/desktop             apps/web
          Tauri                   Browser
             │                     │
       DesktopAdapter           WebAdapter
```

---

# Stage A — Shared Production Frontend Foundation

## UI Phase 0 — Baseline Freeze

Không sửa production UI ở phase này.

### Inventory

Kiểm tra:

```text
apps/desktop/
apps/web/
apps/api/
core/windagent_core/domain/video_production/
core/windagent_core/contracts/video_production/
storage/
workflows/
orchestration/
```

Capture:

```text
baseline_sha
desktop_tests
web_tests
api_tests
video_production_tests

existing_api_contracts
existing_events
existing_frontend_state
```

Đặc biệt phải xác nhận không làm hỏng:

```text
Dashboard
Agents
Agent Workspace
Workflows
Browser
Files
Memory
Models
Router
Settings
```

Desktop hiện đã có page shell và sidebar tương đối hoàn chỉnh nên sẽ dùng nó làm reference shell ban đầu. Không được phá giao diện hiện hữu chỉ để thêm Production.

### Gate

```text
VP3D_UI_P0_BASELINE_FROZEN
```

---

# UI Phase 1 — Frontend Workspace Foundation

Lựa chọn `1C` yêu cầu tạo frontend workspace thật sự.

Tôi đề xuất:

```text
frontend/
├── package.json
├── package-lock.json
└── packages/
    ├── production-contracts/
    ├── production-client/
    ├── production-state/
    ├── production-ui/
    └── production-platform/
```

Hoặc nếu muốn giữ package ở root:

```text
packages/
├── production-contracts/
├── production-client/
├── production-state/
└── production-ui/
```

Tôi ưu tiên **`frontend/packages/`** để không trộn package TypeScript với Python workspace.

### Chuẩn hóa toolchain

Hai frontend hiện không hoàn toàn đồng nhất.

Cần pin chung:

```text
Node version
TypeScript version
React version
Vitest version
Testing Library
ESLint
Vite
```

Không cần ép `apps/desktop` và `apps/web` thành cùng một application.

Chỉ ép:

```text
shared package ABI
shared TypeScript target compatibility
shared test conventions
```

### Gate

```text
VP3D_UI_P1_FRONTEND_WORKSPACE_VERIFIED
```

---

# UI Phase 2 — Platform Adapter Boundary

Đây là bắt buộc vì desktop và web có khả năng khác nhau.

Không để component production gọi:

```ts
window.__TAURI__
```

trực tiếp.

Tạo:

```ts
interface ProductionPlatformAdapter {
    selectLocalFile(): Promise<SelectedFile[]>
    revealFile?(artifactId: string): Promise<void>
    openExternal(url: string): Promise<void>
    downloadArtifact(id: string): Promise<void>
    supportsLocalFilesystem(): boolean
}
```

Implement:

```text
DesktopProductionPlatformAdapter
    ↓
Tauri APIs

WebProductionPlatformAdapter
    ↓
browser File API
    ↓
HTTP upload/download
```

Ví dụ Asset Manager:

### Desktop

```text
Import
  ↓
Select D:\assets\bunny.glb
  ↓
upload/import through backend
```

### Web

```text
Import
  ↓
<input type=file>
  ↓
HTTP upload
```

Không để production domain biết file nằm ở đâu.

### Gate

```text
VP3D_UI_P2_PLATFORM_BOUNDARY_VERIFIED
```

---

# UI Phase 3 — Production Project Context

Tạo shared state:

```ts
ProductionProjectContext {
    projectId
    projectStatus

    revisionId
    revisionStatus

    screenplayId
    screenplayStatus

    currentSequence

    syncStatus
    backendStatus
}
```

Một project context phải dùng xuyên:

```text
Script
Assets
Video
```

Không cho:

```text
Script   → Project A
Assets   → Project B
Video    → Project C
```

trong cùng production workspace mà không có explicit project switch.

UI shell:

```text
┌────────────────────────────────────────────────────────┐
│ Bunny Episode 01                         Backend ●     │
│ Revision 12 · DRAFT · Sequence 2841                    │
├────────────────────────────────────────────────────────┤
│ Script | Assets | Video                                │
└────────────────────────────────────────────────────────┘
```

---

# UI Phase 4 — Production Routing

Sidebar:

```text
Production
├── Script
├── Assets
└── Video
```

Routes logical:

```text
/production/:projectId/script
/production/:projectId/assets
/production/:projectId/video
```

Ngay cả khi app hiện vẫn sử dụng `activeTab`, Production module không nên tiếp tục phụ thuộc vào string switch dài hạn.

Shared routing contract phải cho phép desktop/web map cùng deep-link:

```text
ProductionRoute {
    projectId
    page
    entityId?
    revisionId?
}
```

Ví dụ:

```text
/production/vp_01/script?scene=sc_07
```

hoặc:

```text
/production/vp_01/assets?asset=asset_bunny
```

để Script ↔ Assets ↔ Video cross-navigation được.

### Gate

```text
VP3D_UI_P4_PRODUCTION_NAVIGATION_VERIFIED
```

---

# Stage B — Production API Foundation

## UI Phase 5 — Production Query API

Production Workspace API hiện có các ý tưởng đúng như:

```text
revision_id
idempotency
stale revision rejection
workspace snapshot
```

nhưng implementation hiện vẫn giữ revision/idempotency trong memory nên chỉ phù hợp PoC.

Phải thay bằng application services/repositories thật.

### Project snapshot

```http
GET /api/v2/video-production/projects/{project_id}
```

### Production snapshot

```http
GET /api/v2/video-production/projects/{project_id}/workspace
```

Output:

```json
{
  "project_id": "...",
  "project_status": "...",
  "revision_id": "...",
  "revision_status": "...",
  "screenplay": {},
  "asset_summary": {},
  "pipeline_summary": {},
  "current_sequence": 1234
}
```

Không trả internal filesystem path.

---

# UI Phase 6 — Canonical Command API

Không tạo API kiểu:

```text
PUT /scene
PATCH /dialogue
PUT /asset
PATCH /license
...
```

rải rác.

Mutation production dùng canonical command envelope:

```json
{
  "command_type": "UPDATE_SCENE",
  "project_id": "vp_001",
  "target_revision_id": "rev_012",
  "entity_id": "scene_04",
  "reason": "Manual screenplay edit",
  "payload": {}
}
```

Header:

```text
X-Idempotency-Key
```

Server:

```text
validate revision
↓
validate command
↓
domain rule
↓
persist
↓
emit event
↓
return updated revision
```

Conflict:

```text
HTTP 409
REJECTED_STALE
```

Frontend:

```text
DO NOT retry blindly
```

mà:

```text
reload latest revision
↓
calculate conflict
↓
show human merge UI
```

---

# UI Phase 7 — Real-time Production Synchronization

Backend đã có cả:

```text
/api/v2/events/stream
/api/v2/events/ws
```

cùng replay bằng `last_sequence`.

Shared package phải dùng nó thật.

Architecture:

```text
GET snapshot
     │
     ▼
snapshot.current_sequence = 490
     │
     ▼
connect stream(last_sequence=490)
     │
     ▼
491
492
493
     │
 connection lost
     │
     ▼
reconnect(last_sequence=493)
     │
     ▼
494 replay
495 replay
496 live
```

State update phải idempotent.

Frontend cần:

```text
CONNECTED
RECONNECTING
REPLAYING
STALE
OFFLINE
```

Không dùng random polling để giả realtime.

### Gate

```text
VP3D_UI_P7_REALTIME_STATE_VERIFIED
```

---

# Stage C — Screenplay Workspace

# UI Phase 8 — Screenplay Read Model

Domain hiện có sẵn:

```text
CreativeBrief
StoryConcept
DialogueLine
Screenplay
Scene
```

và `Screenplay` đã chứa ordered scene collection.

Tạo query projection tối ưu frontend:

```text
ScreenplayWorkspaceView
├── screenplay
├── scenes
├── dialogue
├── characters
├── locations
├── validation
├── estimated_duration
├── revision
└── downstream_bindings
```

Không bắt frontend phải gọi 20 endpoint rồi tự join.

---

# UI Phase 9 — Script Workspace Layout

Canonical layout:

```text
┌─────────────────────────────────────────────────────────────────┐
│ PROJECT / REVISION / LOCK STATE / VALIDATION / SAVE            │
├────────────────┬─────────────────────────────┬──────────────────┤
│                │                             │                  │
│ STORY TREE     │ SCRIPT EDITOR               │ INSPECTOR        │
│                │                             │                  │
│ Act 1          │ SCENE 4                     │ Scene            │
│ ├ Scene 1      │ INT. BEDROOM - DAY          │ Characters       │
│ ├ Scene 2      │                             │ Location         │
│ ├ Scene 3      │ Bunny enters...             │ Assets           │
│ └ Scene 4 ◀    │                             │ Validation       │
│                │ BUNNY                       │ Production       │
│ + Scene        │ Good morning...             │ impact           │
│                │                             │                  │
├────────────────┴─────────────────────────────┴──────────────────┤
│ AI / Diff / Warnings / Timeline                                │
└─────────────────────────────────────────────────────────────────┘
```

---

# UI Phase 10 — Structured Screenplay Editor

Mode:

```text
STRUCTURED
```

cho phép edit:

```text
Screenplay
├── title
├── logline
│
├── Scene
│   ├── title
│   ├── location
│   ├── time_of_day
│   ├── action
│   ├── characters
│   └── dialogue
│
└── metadata
```

Scene actions:

```text
Add
Delete
Duplicate
Split
Merge
Move Up
Move Down
Drag Reorder
```

Dialogue:

```text
Character
Dialogue Text
Delivery
Order
```

Validation realtime:

```text
unknown_character
missing_location
duplicate_order
invalid_dialogue_reference
```

---

# UI Phase 11 — Text Screenplay Editor

Vì chọn `2C`, thêm:

```text
TEXT MODE
```

nhưng đây **không phải canonical source of truth riêng**.

Architecture:

```text
Structured Screenplay
       │
       ▼
ScreenplaySerializer
       │
       ▼
Text Representation
```

User edit:

```text
Text
 ↓
ScreenplayParser
 ↓
Candidate Structured Model
 ↓
Validation
 ↓
Diff
 ↓
Apply
```

Không bao giờ:

```text
textarea string
    ↓
ghi thẳng DB
```

Text mode nên dùng format screenplay rõ ràng:

```text
INT. BUNNY HOUSE - MORNING

Bunny walks into the room.

BUNNY
Good morning!

FOX
Morning.
```

---

# UI Phase 12 — Hybrid Mode Round-trip Contract

Đây là acceptance gate riêng.

Test:

```text
Structured A
    ↓
serialize
    ↓
Text
    ↓
parse
    ↓
Structured B
```

Yêu cầu:

```text
semantic(A) == semantic(B)
```

Stable IDs không được biến mất chỉ vì chuyển mode.

Có thể sử dụng invisible mapping metadata ở client/session hoặc backend parser mapping.

Test:

```text
scene IDs stable
character references stable
dialogue IDs stable
order stable
metadata preserved
```

Nếu parser không chắc chắn:

```text
PARSE_REQUIRES_REVIEW
```

Không đoán.

---

# UI Phase 13 — Screenplay Draft Editing

DRAFT:

```text
rev_013 DRAFT
       ↓
manual edit
       ↓
validated command
       ↓
rev_013 DRAFT
```

Có local unsaved buffer:

```text
SERVER
LOCAL_MODIFIED
SAVING
SAVED
CONFLICT
```

Không autosave từng keystroke thành ProductionRevision.

Nên debounce local editing nhưng explicit persistence theo edit unit.

---

# UI Phase 14 — Immutable LOCKED Revision

Quyết định `3B` được coi là invariant.

```text
rev_012 LOCKED
       │
       │ user edits
       ▼
CREATE_REVISION
       │
       ▼
rev_013 DRAFT
       │
       ▼
apply change
```

Tuyệt đối cấm:

```text
LOCKED → mutable
```

UI phải hiển thị:

```text
Editing revision 13
Derived from locked revision 12
```

History:

```text
rev_10 LOCKED
   ↓
rev_11 LOCKED
   ↓
rev_12 LOCKED
   ↓
rev_13 DRAFT
```

---

# UI Phase 15 — Revision Comparison

Cho phép:

```text
rev_12 ↔ rev_13
```

Diff cấp:

```text
screenplay
scene
action
dialogue
character binding
location
```

Không chỉ text diff.

Ví dụ:

```text
Scene 7

Location:
- classroom
+ playground

Dialogue:
- 3 lines
+ 5 lines

Characters:
+ bunny_02
```

---

# UI Phase 16 — Production Impact Analyzer

Domain đã có `InvalidationIntent`, bao gồm invalidation shot plan/generation/assets/all.

Mở rộng thành:

```text
ScreenplayChangeImpact
├── changedScenes
├── changedDialogue
├── changedCharacters
├── changedLocations
├── affectedShots
├── affectedAudio
├── affectedAnimation
├── affectedAssets
├── affectedRenders
└── invalidationIntent
```

UI trước khi commit:

```text
This change affects

Scenes               2
Shots                7
Dialogue tracks      4
TTS tracks           4
Animation tracks     3
Assets               0
Rendered shots       7
```

Actions:

```text
[Cancel]
[Create Revision & Apply]
```

---

# UI Phase 17 — AI-assisted Screenplay Editing

Không cho LLM mutate canonical screenplay.

Pipeline:

```text
selection
   ↓
AI instruction
   ↓
ScriptRevisionProposal
   ↓
domain validation
   ↓
semantic diff
   ↓
human review
   ↓
APPROVE / REJECT
```

UI actions:

```text
Rewrite
Shorten
Expand
Change Tone
Improve Dialogue
Fix Continuity
Rewrite Scene
Review Episode
```

Repository hiện đã có proposal lifecycle `PENDING / APPROVED / REJECTED`, nên nên tái sử dụng semantics này.

---

# UI Phase 18 — Screenplay Validation Gate

Before lock:

```text
ScreenplayValidator
```

checks:

```text
scene order
missing location
unknown character
dialogue integrity
duration
continuity
story constraints
production constraints
required references
```

UI:

```text
BLOCKING  2
WARNING   5
INFO      8
```

Rule:

```text
BLOCKING > 0
    ↓
LOCK DISABLED
```

Lock:

```text
DRAFT
 ↓
VALIDATE
 ↓
LOCKED
```

### Gate

```text
VP3D_UI_SCRIPT_WORKSPACE_VERIFIED
```

---

# Stage D — Universal Production Asset Domain

# UI Phase 19 — Production Asset Taxonomy

Quyết định `4B` đồng nghĩa `ReferenceAsset` hiện tại chưa đủ.

Model hiện tại chủ yếu mô tả content-addressed media và provenance.

Không phá `MediaType`.

Thêm:

```python
ProductionAssetKind
```

Canonical taxonomy:

```text
CHARACTER
ENVIRONMENT
PROP

MODEL_3D
MATERIAL
TEXTURE

RIG
ANIMATION
FACIAL_PROFILE

VOICE_PROFILE
VOICE_SAMPLE
DIALOGUE_AUDIO

MUSIC
SFX
AMBIENCE

LIGHT_RIG
CAMERA_RIG

REFERENCE_IMAGE
STORYBOARD

DOCUMENT
OTHER
```

Tách rõ:

```text
ProductionAssetKind = meaning
MediaType           = physical representation
MimeType            = file encoding
```

Ví dụ:

```text
kind        CHARACTER
media       MODEL_3D
mime        model/gltf-binary
```

---

# UI Phase 20 — Asset Aggregate

Tạo:

```text
ProductionAsset
├── asset_id
├── kind
├── name
├── description
├── lifecycle
├── active_revision_id
├── tags
├── source
├── license
├── project_bindings
├── dependencies
└── metadata
```

Và:

```text
AssetRevision
├── revision_id
├── asset_id
├── content_hash
├── format
├── normalized_format
├── preview_artifacts
├── validation_report
├── provenance
├── created_at
└── supersedes
```

Không overwrite bytes.

---

# UI Phase 21 — Asset Lifecycle

Giữ state machine hiện tại:

```text
DISCOVERED
 ↓
DOWNLOADED
 ↓
VALIDATED
 ├── LICENSE_UNKNOWN
 ├── APPROVED
 └── REJECTED
 ↓
BOUND_TO_PROJECT
```

Repo đã enforce transition fail-closed.

Mở rộng nếu 3D pipeline yêu cầu thêm trạng thái operational thì **không nhét job status vào lifecycle**.

Ví dụ:

```text
AssetLifecycleState
```

khác:

```text
AssetProcessingStatus
```

Processing:

```text
IDLE
DOWNLOADING
NORMALIZING
GENERATING_PREVIEW
VALIDATING
RIGGING
PROCESSING
FAILED
```

---

# UI Phase 22 — Asset Query API

Endpoints:

```http
GET /api/v2/video-production/assets

GET /api/v2/video-production/assets/{asset_id}

GET /api/v2/video-production/assets/{asset_id}/revisions

GET /api/v2/video-production/assets/{asset_id}/validation

GET /api/v2/video-production/assets/{asset_id}/provenance

GET /api/v2/video-production/assets/{asset_id}/bindings

GET /api/v2/video-production/assets/{asset_id}/dependencies
```

Filters:

```text
project_id
kind
lifecycle
processing_status
license
source
format
tag
query
```

Pagination bắt buộc.

Không load toàn asset library vào browser.

---

# UI Phase 23 — Asset Command API

Commands:

```text
IMPORT_ASSET
UPLOAD_ASSET

DISCOVER_ASSET
DOWNLOAD_ASSET

REQUEST_ASSET_GENERATION

NORMALIZE_ASSET
VALIDATE_ASSET

APPROVE_ASSET
REJECT_ASSET
UPDATE_LICENSE

CREATE_ASSET_REVISION

BIND_ASSET
UNBIND_ASSET

ARCHIVE_ASSET
```

Mọi command:

```text
idempotent
revision-aware
auditable
event-emitting
```

---

# UI Phase 24 — Asset Library Page

Layout:

```text
┌──────────────────────────────────────────────────────────────────┐
│ ASSET LIBRARY          Search                  Import / Generate │
├──────────────┬─────────────────────────────┬─────────────────────┤
│ FILTERS      │ LIBRARY                    │ INSPECTOR           │
│              │                            │                     │
│ Character    │ Bunny      Fox             │ Bunny               │
│ Environment  │ Classroom  Park            │ CHARACTER           │
│ Props        │ Chair      Book            │ APPROVED            │
│ Animation    │ Walk       Run             │ Revision 3          │
│ Voice        │ Bunny V1   Fox V2           │                     │
│ Audio        │                            │ Preview             │
│ Lighting     │                            │                     │
│ Camera       │                            │ Validation          │
│              │                            │ Provenance          │
│ Approved     │                            │ Usage               │
│ Quarantine   │                            │ Dependencies        │
└──────────────┴─────────────────────────────┴─────────────────────┘
```

Views:

```text
Grid
List
```

---

# UI Phase 25 — Asset Inspector

Tabs:

```text
Overview
Preview
Versions
Validation
Provenance
License
Dependencies
Usage
```

## Overview

```text
Asset ID
Kind
Format
Size
Hash
Lifecycle
Active revision
Created
```

## Validation

```text
Mesh                PASS
Normals             PASS
UV                   PASS
Texture             WARNING
Rig                  PASS
Polycount            WARNING
VRAM estimate        PASS
```

## Provenance

```text
source
provider
author
URL
model
prompt_hash
seed
generated_at
downloaded_at
```

---

# UI Phase 26 — Asset License Governance

Unknown license:

```text
LICENSE_UNKNOWN
```

UI:

```text
⚠ This asset cannot be used in final production.

Source:
...

License:
UNKNOWN

[Attach License]
[Reject Asset]
```

Không có:

```text
Use Anyway
```

trừ khi sau này có explicit human override policy.

Final production phải fail closed.

---

# UI Phase 27 — 3D Preview System

Không mở Blender cho mỗi preview.

Pipeline:

```text
FBX/USD/.blend/glTF
       ↓
Preview Compiler
       ↓
GLB derivative
       ↓
Web renderer
```

Shared UI:

```text
Three.js / React Three Fiber
```

Capabilities:

```text
orbit
zoom
pan
wireframe
skeleton
bounding box
materials
texture toggle
animation playback
statistics
```

Desktop và web dùng cùng viewer.

Blender `.blend` không parse trực tiếp trong frontend.

---

# UI Phase 28 — Non-3D Resource Preview

Do Asset Manager quản lý toàn production resources:

### Image

```text
image viewer
```

### Voice/audio/music/SFX

```text
waveform
playback
duration
sample rate
```

### Animation

```text
3D character preview
animation playback
```

### Material

```text
material sphere preview
```

### Camera rig

```text
metadata + optional preview
```

### Lighting rig

```text
rendered thumbnail
```

---

# UI Phase 29 — Asset Acquisition Workspace

`+ Add Asset`:

```text
Upload Local
Import URL
Search Internet
Generate with Agent
Reuse Existing
```

Internet/generation flow:

```text
AssetRequirement
       │
       ▼
AssetResolverPort
       ├── Local
       ├── Internet
       ├── Mesh API
       ├── Mesh MCP
       └── Future Generator
```

Frontend không chọn arbitrary implementation unless user explicitly requests provider.

---

# UI Phase 30 — Asset Generation Request

Form:

```text
Type:
Character

Description:
Small friendly rabbit...

Style:
3D cartoon

Rig Required:
Yes

Target:
Children animation

Polygon budget:
...

Texture budget:
...
```

Submit:

```text
AssetGenerationRequest
```

Then:

```text
QUEUED
 ↓
GENERATING
 ↓
DOWNLOADED
 ↓
NORMALIZING
 ↓
VALIDATING
 ↓
LICENSE CHECK
 ↓
READY / QUARANTINED / FAILED
```

---

# UI Phase 31 — Asset Job Monitor

Asset Library cards can show:

```text
Bunny

NORMALIZING
██████████░░ 81%

Mesh         ✓
Textures     ✓
Rig          ...
Preview      waiting
```

Job detail:

```text
job_id
provider
status
current_stage
progress
started_at
duration
logs
failure
retry policy
```

Actions:

```text
Cancel
Retry
Inspect failure
```

không retry mù.

---

# UI Phase 32 — Asset Usage & Dependency Graph

Asset inspector:

```text
Bunny Character
│
├── Episode 01
│   ├── Scene 02
│   │   ├── Shot 04
│   │   └── Shot 05
│   └── Scene 08
│
└── Episode 02
    └── Scene 01
```

Dependency graph:

```text
Character Bunny
├── Mesh bunny_v3
├── Material bunny_body
├── Texture bunny_albedo
├── Rig bunny_rig_v2
├── FacialProfile bunny_face
└── VoiceProfile bunny_voice
```

---

# UI Phase 33 — Asset Version Replacement

Nếu:

```text
Bunny rev_3
      ↓
Bunny rev_4
```

không được tự thay trong mọi episode.

UI phải tính:

```text
Affected Projects
Affected Scenes
Affected Shots
Affected Animations
Potential rerenders
```

Actions:

```text
Update only current project
Update selected bindings
Create project revision
Cancel
```

---

# Stage E — Script ↔ Asset Integration

# UI Phase 34 — Entity Binding

Script Inspector:

```text
Characters
Bunny     ✓ asset bound
Fox       ⚠ missing asset

Location
Playground ✓

Props
Ball      ✓
Bench     ⚠ missing
```

Click missing:

```text
Resolve Asset
```

→ Asset Manager với prefilled requirement.

---

# UI Phase 35 — Cross Navigation

Script:

```text
Bunny
 ↓ click
Assets / Bunny
```

Asset:

```text
Used in Scene 07
 ↓ click
Script / Scene 07
```

URLs/deep-links phải preserve:

```text
projectId
revisionId
entityId
```

---

# UI Phase 36 — Missing Asset Resolver

Screenplay validation có thể tạo:

```text
AssetRequirement[]
```

UI sidebar:

```text
Production Resources

Characters   3 / 3
Locations    2 / 2
Props        8 / 10

Missing:
- toy_train
- blue_table
```

Actions:

```text
Search Library
Search Internet
Generate
Upload
```

Đây là bridge trực tiếp giữa screenplay và roadmap Asset Pipeline Phase 5–7.

---

# Stage F — Human + Agent Collaboration

# UI Phase 37 — Unified Change Proposal

AI không được trực tiếp mutate:

```text
Screenplay
Asset Binding
License
Asset Approval
```

Tất cả sensitive AI changes:

```text
Proposal
 ↓
Preview
 ↓
Impact
 ↓
Human approval
```

Một proposal có:

```text
proposal_id
proposal_type
target_revision
affected_entities
diff
impact
created_by_agent
status
```

---

# UI Phase 38 — Production Activity Timeline

Cả Script và Assets dùng chung:

```text
12:42 Screenplay rev_13 created
12:43 Scene 4 edited
12:44 Asset Bunny approved
12:45 TTS invalidated for Scene 4
12:46 Bunny rev_4 generated
```

Không phải generic debug logs.

Đây là human-readable production history.

---

# Stage G — Offline / Recovery / Conflict Handling

# UI Phase 39 — Frontend State Recovery

Shared state cần persist:

```text
project
page
selected scene
selected asset
active editor mode
last_sequence
unsaved local draft
```

Sau restart:

```text
open desktop/web
 ↓
restore project
 ↓
fetch server snapshot
 ↓
compare revision
 ↓
replay events
```

Không apply cached data mù.

---

# UI Phase 40 — Concurrent Edit Conflict

Ngay cả single-user system vẫn có conflict vì:

```text
Agent
Worker
Frontend
Automation
```

cùng có thể tạo revision.

Nếu:

```text
UI edits rev_12
```

nhưng backend đã ở:

```text
rev_13
```

server:

```text
409 STALE_REVISION
```

UI:

```text
Your revision: 12
Current:       13

[View Changes]
[Merge Into New Revision]
[Discard Local Changes]
```

---

# Stage H — Testing

# UI Phase 41 — Contract Tests

Shared TS contracts phải test với API JSON fixtures.

Detect:

```text
backend adds field       OK
backend removes required field FAIL
enum mismatch            FAIL
invalid revision         FAIL
```

Không duplicate handwritten backend DTOs lâu dài nếu có thể generate JSON Schema/OpenAPI types.

---

# UI Phase 42 — Script Behavioral Tests

Test:

```text
load screenplay
select scene
structured edit
text edit
round trip
add scene
delete scene
reorder
locked revision
revision creation
AI proposal
impact warning
validation
lock
stale conflict
reconnect
```

---

# UI Phase 43 — Asset Behavioral Tests

Test:

```text
list
search
filter
import
preview
validate
license unknown
approve
reject
version
binding
unbinding
dependency
job progress
failure
retry
cross-navigation
```

---

# UI Phase 44 — Shared Package Consumer Tests

Cùng test suite phải chạy dưới:

```text
apps/desktop
apps/web
```

để chứng minh shared package không vô tình phụ thuộc Tauri.

Gate:

```text
production-ui browser test PASS
production-ui desktop test PASS
```

---

# UI Phase 45 — Desktop E2E

Canonical test:

```text
Launch Tauri
 ↓
open Production
 ↓
select project
 ↓
Script
 ↓
edit screenplay
 ↓
create revision
 ↓
Assets
 ↓
import GLB
 ↓
validate
 ↓
bind to character
 ↓
restart app
 ↓
state recovered
```

---

# UI Phase 46 — Browser E2E

Test tương tự nhưng:

```text
no Tauri
no filesystem path
no native assumptions
```

Import qua:

```text
File API + HTTP
```

---

# Stage I — Final Acceptance

# UI Phase 47 — Script Golden Workflow

```text
Create screenplay
 ↓
Structured edit
 ↓
Text edit
 ↓
AI revision proposal
 ↓
Human approve
 ↓
Validation
 ↓
Lock
 ↓
Edit locked screenplay
 ↓
New revision created
```

Gate:

```text
VP3D_UI_SCRIPT_GOLDEN_WORKFLOW_PASSED
```

---

# UI Phase 48 — Asset Golden Workflow

```text
Asset requirement
 ↓
Acquire/generate
 ↓
Normalize
 ↓
Validate
 ↓
License
 ↓
Preview
 ↓
Approve
 ↓
Bind
 ↓
Use in project
 ↓
Create asset revision
 ↓
Impact review
```

Gate:

```text
VP3D_UI_ASSET_GOLDEN_WORKFLOW_PASSED
```

---

# UI Phase 49 — Script + Asset Integrated E2E

Golden scenario:

```text
Screenplay Scene 03
requires:
Bunny
Park
Ball

        ↓

Bunny exists
Park exists
Ball missing

        ↓

Asset Manager
Generate Ball

        ↓

normalize
validate
approve

        ↓

bind Ball → Scene 03

        ↓

Screenplay validation

        ↓

LOCK
```

No direct database changes.
No direct JSON modifications.
No manual filesystem copying.

Gate:

```text
VP3D_UI_SCRIPT_ASSET_INTEGRATION_PASSED
```

---

# UI Phase 50 — Foundation for Video Production Page

Chưa xây Video page trong Roadmap II này.

Nhưng trước khi kết thúc phải đảm bảo shared infrastructure hỗ trợ:

```text
ProductionProjectContext
ProductionRevisionContext
Event Stream
Jobs
Asset Binding
Shot IDs
Scene IDs
Artifact Preview
Approval
Invalidation
```

Video page sau này chỉ cần thêm:

```text
packages/production-ui/video/
```

thay vì kiến trúc frontend lần ba.

Gate:

```text
VP3D_UI_VIDEO_WORKSPACE_FOUNDATION_READY
```

---

# Package structure cuối

```text
frontend/
├── package.json
│
└── packages/
    │
    ├── production-contracts/
    │   ├── project.ts
    │   ├── screenplay.ts
    │   ├── asset.ts
    │   ├── revision.ts
    │   ├── command.ts
    │   ├── event.ts
    │   └── job.ts
    │
    ├── production-client/
    │   ├── projectClient.ts
    │   ├── screenplayClient.ts
    │   ├── assetClient.ts
    │   ├── commandClient.ts
    │   └── eventClient.ts
    │
    ├── production-state/
    │   ├── projectStore.ts
    │   ├── screenplayStore.ts
    │   ├── assetStore.ts
    │   ├── eventProjection.ts
    │   └── recovery.ts
    │
    ├── production-platform/
    │   └── types.ts
    │
    └── production-ui/
        │
        ├── common/
        │
        ├── screenplay/
        │   ├── ScreenplayWorkspace.tsx
        │   ├── StructuredEditor.tsx
        │   ├── TextEditor.tsx
        │   ├── SceneTree.tsx
        │   ├── SceneInspector.tsx
        │   ├── ScreenplayDiff.tsx
        │   ├── ValidationPanel.tsx
        │   └── ImpactPanel.tsx
        │
        └── assets/
            ├── AssetWorkspace.tsx
            ├── AssetGrid.tsx
            ├── AssetList.tsx
            ├── AssetInspector.tsx
            ├── AssetPreview.tsx
            ├── AssetVersionHistory.tsx
            ├── AssetValidation.tsx
            ├── AssetProvenance.tsx
            ├── AssetLicense.tsx
            ├── AssetDependencies.tsx
            └── AssetJobPanel.tsx
```

Apps:

```text
apps/desktop/
└── src/production/
    ├── DesktopProductionAdapter.ts
    └── ProductionPage.tsx

apps/web/
└── src/production/
    ├── WebProductionAdapter.ts
    └── ProductionPage.tsx
```

---

# Dependency graph giữa Roadmap I và Roadmap II

```text
ROADMAP I                         ROADMAP II

P0 Baseline ──────────────────── UI0

P1 Production IR ─────────────── UI3 / UI5 / UI6

Screenplay Domain ────────────── UI8
                                  ↓
                                UI9–18

P5 Asset Gateway ─────────────── UI29–31
P6 Provenance ────────────────── UI25–26
P7 Asset Normalization ───────── UI21 / UI25

P8 Character ─────────────────── UI19 / UI27
P9 Rig ───────────────────────── UI27

P10 Audio ────────────────────── UI19 / UI28

P15 Animation ────────────────── UI19 / UI27

P19 Renderer ─────────────────── Video UI later

P21 Render Jobs ──────────────── shared Job UI

P25 Golden Scene ─────────────── future full Production E2E
```

---

# Các phase có thể chạy song song

Sau UI7:

```text
                  UI8
                   │
          ┌────────┴─────────┐
          ▼                  ▼
    SCRIPT TRACK         ASSET TRACK

      UI9                  UI19
       ↓                    ↓
      UI10                 UI20
      ├ UI11               UI21
      ↓                    ↓
      UI12                 UI22
       ↓                    ↓
      UI13                 UI23
       ↓                    ↓
      UI14                 UI24
       ↓                    ↓
      UI15                 UI25
       ↓                    ↓
      UI16                 UI26
       ↓                    ↓
      UI17                 UI27
       ↓                    ↓
      UI18                 UI28–33
          \                /
           \              /
            ▼            ▼
               UI34–40
                   ↓
               UI41–50
```

Do đó **Script Workspace và Asset Manager không cần làm tuần tự**.

---

# Critical Path

Nếu ưu tiên nhanh nhất để thấy sản phẩm hoạt động:

```text
UI0
 ↓
UI1
 ↓
UI2
 ↓
UI3
 ↓
UI5
 ↓
UI6
 ↓
UI7
 ↓
UI8
 ↓
UI9
 ↓
UI10
 ↓
UI13
 ↓
UI14
 ↓
UI18
```

Kết quả:

```text
Script Workspace V1 usable
```

Song song:

```text
UI19
 ↓
UI20
 ↓
UI21
 ↓
UI22
 ↓
UI23
 ↓
UI24
 ↓
UI25
 ↓
UI26
```

Kết quả:

```text
Asset Manager V1 usable
```

Sau đó:

```text
UI27–33
 ↓
UI34–40
 ↓
UI41–49
```

---

# Milestones

| Milestone | Kết quả                                |
| --------- | -------------------------------------- |
| F-M1      | Shared frontend workspace              |
| F-M2      | Desktop/Web dùng cùng Production UI    |
| F-M3      | Production API + event synchronization |
| F-M4      | Script structured editor               |
| F-M5      | Script text editor                     |
| F-M6      | Hybrid round-trip verified             |
| F-M7      | Immutable screenplay revision          |
| F-M8      | AI revision proposal                   |
| F-M9      | Universal Asset Library                |
| F-M10     | Provenance/license governance          |
| F-M11     | 3D/audio/material previews             |
| F-M12     | Asset generation/job monitoring        |
| F-M13     | Script ↔ Asset binding                 |
| F-M14     | Desktop/Web E2E                        |
| F-M15     | Video Workspace foundation ready       |

---

# Nguyên tắc bắt buộc

## 1. ProductionRevision là ranh giới sửa đổi

```text
LOCKED = immutable
```

Không có ngoại lệ UI.

## 2. UI không phải source of truth

```text
backend domain
=
source of truth
```

## 3. `.blend` không phải source of truth

Đúng theo Roadmap I.

## 4. AI không mutate canonical state trực tiếp

```text
AI
 ↓
Proposal
 ↓
Validation
 ↓
Human/Policy approval
 ↓
Command
```

## 5. Asset không rõ license không được final render

Fail closed.

## 6. Không copy Production UI giữa Desktop và Web

Shared package bắt buộc.

## 7. Platform-specific code chỉ nằm ở adapter

```text
Tauri ≠ Production UI
Browser ≠ Production UI
```

## 8. Screenplay text mode không tạo source of truth thứ hai

```text
Text
↔
Structured screenplay
```

phải round-trip qua parser/serializer.

---

# Verdict kiến trúc

Sau khi khóa bốn lựa chọn, kiến trúc frontend chính thức nên là:

```text
                     WindAgent
                        │
                        ▼
               Production API V2
                        │
                 Domain + Events
                        │
                        ▼
           Shared Production Frontend
                        │
       ┌────────────────┼────────────────┐
       │                │                │
       ▼                ▼                ▼
     Script           Assets           Video
   Workspace          Manager          Future
       │                │
       └────────────────┼────────────────┘
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
          Desktop                 Web
           Tauri                 Browser
```

Roadmap II vì thế **không phải “thêm hai page React”**. Nó là việc bổ sung **Human Production Control Layer** còn thiếu giữa WindAgent production domain và người dùng.

Phần này nên được triển khai song song với Roadmap Blender/3D, bắt đầu từ **UI0 → UI7**, sau đó tách hai nhánh **UI8–18 Script** và **UI19–33 Assets** chạy đồng thời.
