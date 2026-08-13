Dựa trên inventory hiện tại, phần **runtime của Studio đã tương đối hoàn chỉnh**, còn phần cần tái cấu trúc chủ yếu là presentation architecture: `App.tsx`, `StudioPage.tsx`, `ArtifactViews.tsx`, navigation và `styles.css`. Đồng thời các package `studio-contracts`, `studio-client`, `studio-state`, API V3 và worker phải được giữ ổn định.  Kế hoạch dưới đây bám theo mục tiêu Roadmap 1: đưa người dùng đi xuyên suốt **Series → Episode → Idea → Story → Outline → Screenplay → Review → Approval → Lock → READY_FOR_PRODUCTION**, thay vì biến Desktop thành một general-purpose agent console có thêm tab Studio. 

# WindAgent Studio — Desktop Redesign Roadmap

## 1. Mục tiêu cuối

Sau khi hoàn thành, Desktop phải có kiến trúc:

```text
WindAgent Desktop
│
├── Tauri Shell                         KEEP
│
└── React Application
    │
    ├── studio-shell
    │   ├── AppShell
    │   ├── TopBar
    │   ├── Sidebar
    │   ├── Navigation
    │   ├── WorkspaceHeader
    │   └── RouteOutlet
    │
    ├── Studio
    │   ├── Studio Home
    │   ├── Series
    │   ├── Episodes
    │   ├── Episode Workspace
    │   └── Approvals
    │
    ├── story-ui
    │   ├── Idea
    │   ├── Story
    │   ├── Outline
    │   ├── Screenplay
    │   ├── Review
    │   ├── Revision
    │   └── Approval / Lock
    │
    ├── Production                      ROADMAP 2 / COLLAPSED
    │
    └── System
        ├── Agent Workspace
        ├── Models
        ├── Router / Providers
        ├── Browser
        ├── Files
        └── Settings
```

Data path không thay đổi:

```text
UI
 ↓
StudioStore
 ↓
HttpStudioApiClient
 ↓
/api/v3/studio
 ↓
OrchestratorService
 ↓
Worker
 ↓
Story runtime
```

---

# 2. Nguyên tắc triển khai

Toàn bộ redesign phải tuân theo:

```text
PRESENTATION REFACTOR > RUNTIME REWRITE

MOVE / EXTRACT > REIMPLEMENT

SERVER AUTHORITY > FRONTEND SYNTHESIS

EXISTING CONTRACT > NEW CONTRACT

INCREMENTAL MIGRATION > BIG BANG REWRITE
```

### Không được chạm trong roadmap UI

```text
frontend/packages/studio-contracts/*
apps/api/windagent_api/routers/v3/studio/*
apps/api/.../studio_* services
apps/worker/windagent_worker/studio_runtime.py
story runtime task contracts
Roadmap 1 gate evidence
Production runtime
ProductionEngine
Blender
Unreal
```

`studio-client` và `studio-state` chỉ sửa khi có defect thực sự được chứng minh; redesign không phải lý do để thay chúng.

---

# 3. Tổng thể execution plan

| Phase | Mục tiêu                              | Phụ thuộc        |
| ----- | ------------------------------------- | ---------------- |
| UI0   | Freeze baseline + redesign contract   | —                |
| UI1   | Design system foundation              | UI0              |
| UI2   | Extract `studio-shell`                | UI1              |
| UI3   | Navigation + routing architecture     | UI2              |
| UI4A  | Extract `story-ui`                    | UI2              |
| UI4B  | Studio Home + Series surfaces         | UI3              |
| UI5   | Episode Workspace foundation          | UI3 + UI4A       |
| UI6   | Idea + Story experience               | UI5              |
| UI7   | Outline + Screenplay experience       | UI6              |
| UI8   | Review + Revision + Approval + Lock   | UI7              |
| UI9   | Runtime status + activity UX          | UI5              |
| UI10  | Production isolation + System regroup | UI3              |
| UI11  | Desktop polish + accessibility        | UI8 + UI9 + UI10 |
| UI12  | Real vertical-slice certification     | UI11             |

UI4A và UI4B có thể chạy song song. UI9 và UI10 cũng có thể chạy song song với UI6–UI8 sau khi shell ổn định.

---

# PHASE UI0 — BASELINE & REDESIGN CONTRACT

## Mục tiêu

Khóa trạng thái hiện tại trước khi sửa UI.

Không bắt đầu bằng `App.tsx`.

### UI0.1 Freeze baseline

Capture:

```text
commit SHA
branch
git status

desktop tests
frontend package tests
desktop typecheck
desktop build
web build

Studio deep-link tests
Studio story tests
production package tests
```

Artifact:

```text
artifacts/studio_refactor/roadmap_01/desktop_redesign/ui0/
├── baseline.json
├── test_matrix.json
├── build_matrix.json
├── dependency_snapshot.json
└── baseline_verdict.md
```

### UI0.2 Freeze behavior contracts

Đặc biệt ghi lại behavior đang hoạt động của:

```text
createSeries
createEpisode
startRun
selectIdea
submitApproval
lockScreenplay

StudioStore polling
cursor persistence
idempotency key
optimistic version
revision hash
lock hash
deep-link hydration
```

Redesign không được làm thay đổi semantics này.

### UI0.3 Canonical API base investigation

Defect hiện tại:

```text
V2 desktop default → 127.0.0.1:8765

Studio default
→ localhost:8000
```

Không sửa ngay bằng search/replace.

Đầu tiên xác định canonical configuration:

```text
VITE_API_BASE
vite dev proxy
production Desktop config
CI config
certification config
```

Target:

```text
ONE DESKTOP API BASE AUTHORITY
```

Nếu cần sửa, tách thành:

```text
UI0-INFRA-01
```

và có test riêng.

### Gate

```text
WIND_STUDIO_UI0_BASELINE_FROZEN
```

---

# PHASE UI1 — DESIGN SYSTEM FOUNDATION

## Mục tiêu

Không tiếp tục thêm CSS vào file `styles.css` 4.800+ dòng mà không có structure.

Nhưng cũng không rewrite CSS toàn app.

## UI1.1 Token inventory

Giữ và chuẩn hóa các token hiện có:

```text
background
surface
surface-elevated
border
text-primary
text-secondary

primary
success
warning
danger
accent
```

Bổ sung semantic token:

```text
--studio-bg
--studio-surface-1
--studio-surface-2

--studio-border
--studio-border-active

--studio-text-primary
--studio-text-muted

--studio-accent

--status-running
--status-waiting
--status-success
--status-failed
--status-locked
```

Không hardcode màu trạng thái story trong component.

## UI1.2 Layout tokens

Thêm authority cho:

```text
sidebar width
header height
workspace padding
panel radius
panel gap
content max width
inspector width
```

## UI1.3 Primitive components

Tạo các primitive UI trước khi redesign pages:

```text
Button
IconButton
Badge
StatusBadge
Panel
Card
EmptyState
SectionHeader
Tabs
ProgressBar
Skeleton
Alert
Dropdown
Tooltip
```

Không cần xây component library khổng lồ.

Chỉ tạo những component thực sự cần cho Studio.

## UI1.4 Icon policy

Loại bỏ dần việc trộn:

```text
emoji
inline SVG
random glyph
```

Chọn một authority icon duy nhất nếu dependency hiện có hỗ trợ.

Nếu phải thêm dependency mới thì cần justification riêng.

### Gate

```text
WIND_STUDIO_UI1_DESIGN_FOUNDATION_READY
```

Acceptance:

```text
existing Desktop still renders
Studio tests PASS
build PASS
no story behavior changes
```

---

# PHASE UI2 — EXTRACT `studio-shell`

Đây là refactor kiến trúc quan trọng nhất.

## Mục tiêu

Biến:

```text
App.tsx
≈ 593 lines
```

từ shell god-file thành composition root.

Target:

```text
App.tsx
   ↓
AppProviders
   ↓
StudioShell
├── TopBar
├── Sidebar
├── MainWorkspace
└── RouteOutlet
```

## UI2.1 Tạo package

```text
frontend/packages/studio-shell/
```

Cấu trúc đề xuất:

```text
studio-shell/
├── src/
│   ├── layout/
│   │   ├── AppShell.tsx
│   │   ├── TopBar.tsx
│   │   ├── Sidebar.tsx
│   │   ├── MainWorkspace.tsx
│   │   └── WorkspaceHeader.tsx
│   │
│   ├── navigation/
│   │   ├── navigation.types.ts
│   │   ├── navigation.config.ts
│   │   └── NavigationGroup.tsx
│   │
│   ├── status/
│   │   ├── BackendStatus.tsx
│   │   ├── RuntimeMetrics.tsx
│   │   └── RuntimeStatusStrip.tsx
│   │
│   └── index.ts
```

## UI2.2 Không move runtime polling ngay

Giai đoạn đầu:

```text
App.tsx
   owns health/metrics
        ↓ props
TopBar
```

Sau khi shell extraction PASS mới cân nhắc hook:

```text
useDesktopRuntimeStatus()
```

Không vừa move layout vừa rewrite polling.

## UI2.3 Version/user cleanup

Các giá trị:

```text
WindAgent v1.2.0
WindUser
Administrator
```

không nên tiếp tục là presentation constants.

Nhưng nếu chưa có runtime authority thì:

```text
REPORT / ADAPT
```

không tự phát minh user/profile system.

### Gate

```text
WIND_STUDIO_UI2_STUDIO_SHELL_EXTRACTED
```

Acceptance:

```text
App.tsx is composition-oriented
header behavior unchanged
metrics behavior unchanged
all existing pages reachable
Studio deep links preserved
```

---

# PHASE UI3 — NAVIGATION & ROUTING RESTRUCTURE

## Mục tiêu

Navigation phải phản ánh product architecture mới.

## Target navigation

```text
STUDIO
├── Home
├── Series
├── Episodes
└── Approvals

PRODUCTION
├── Assets
├── Workspace
└── Renders

SYSTEM
├── Agent Workspace
├── Models
├── Providers / Router
├── Browser
├── Files
└── Settings
```

Không cần đưa:

```text
Idea
Story Bible
Beat Sheet
Outline
Screenplay
```

vào application sidebar.

Chúng thuộc **Episode Workspace**.

## UI3.1 Navigation descriptor

Thay JSX hardcode bằng:

```text
NavigationItem
NavigationGroup
NavigationConfig
```

Ví dụ concept:

```text
STUDIO
PRODUCTION
SYSTEM
```

mỗi item có:

```text
id
label
icon
route
group
status?
visibility?
```

## UI3.2 Preserve legacy surfaces

Các trang fake/broken hiện tại:

```text
Browser
Files
Memory
Workflows
Endpoints
...
```

không sửa chức năng trong phase này.

Có thể:

```text
regroup
hide secondary item
show disabled/beta badge
```

nhưng không giả vờ biến chúng thành production-ready.

## UI3.3 Routing strategy

Không bắt buộc migrate sang React Router.

Giữ hash routing hiện tại nếu đáp ứng:

```text
deep link
refresh rehydration
navigation
back/forward
```

Target URL tối thiểu:

```text
#/studio
#/studio/series/:seriesId
#/studio/episodes/:episodeId
```

Có thể mở rộng:

```text
#/studio/episodes/:episodeId/screenplay
#/studio/episodes/:episodeId/review
```

nếu không phá certification contract.

### Gate

```text
WIND_STUDIO_UI3_NAVIGATION_ARCHITECTURE_VERIFIED
```

---

# PHASE UI4A — EXTRACT `story-ui`

Có thể chạy song song UI4B.

## Mục tiêu

Tách `ArtifactViews.tsx` thành presentation components nhưng không đổi data contract.

Target:

```text
frontend/packages/story-ui/
```

## UI4A.1 Pure extraction đầu tiên

Tách:

```text
IdeaSetView
StoryBibleView
WorldBibleView
CharacterCanonView
BeatsView
OutlineView
ScreenplayView
ReviewReportView
RevisionProposalView
LockReceiptView
LockPackageView
ScreenplayDiffView
RunProgress
ApprovalBar
```

Luật:

```text
NO API calls
NO StudioStore creation
NO direct backend knowledge
```

Input chỉ là:

```text
props
artifact envelopes
callbacks
status
```

## UI4A.2 Story-ui internal grouping

```text
story-ui/
├── idea/
├── story/
├── outline/
├── screenplay/
├── review/
├── revisions/
├── approval/
├── runtime/
└── shared/
```

## UI4A.3 Preserve behavior

Lần extraction đầu:

```text
visual output ≈ current
```

Redesign sâu thực hiện UI6–UI8.

### Gate

```text
WIND_STUDIO_UI4A_STORY_UI_EXTRACTED
```

---

# PHASE UI4B — STUDIO HOME & SERIES EXPERIENCE

## Studio Home

Không còn trang:

```text
"No series yet. Create one below."
```

là toàn bộ trải nghiệm.

Target Studio Home:

```text
Studio Home

[New Series]

Summary
├── Active Series
├── Episodes in Development
├── Locked Screenplays
└── Pending Approvals

Recent Series
Recent Episodes
Pending Work
Recent Activity
```

Không invent metric nếu API không cung cấp.

Các metric không có authoritative data phải bỏ hoặc derive rõ ràng từ returned records.

## Series Detail

Target:

```text
Series Header
├── title
├── description
├── audience
├── language
├── genre
└── status

Episodes
┌───────────────────────────────┐
│ EP001   Story Development     │
│ EP002   Screenplay Review     │
│ EP003   Ready for Production  │
└───────────────────────────────┘
```

Actions:

```text
Create Episode
Open Episode
```

Không thêm action backend chưa support.

### Gate

```text
WIND_STUDIO_UI4B_STUDIO_SERIES_SURFACES_LIVE
```

---

# PHASE UI5 — EPISODE WORKSPACE FOUNDATION

Đây là phase quan trọng nhất về UX.

## Mục tiêu

Một Episode trở thành workspace trung tâm.

Target layout:

```text
┌─────────────────────────────────────────────────────┐
│ Breadcrumb                                          │
│ Series / Episode 001                                │
│                                                     │
│ Episode title          SCREENPLAY_REVIEW            │
│ Duration / revision / run status                    │
├─────────────────────────────────────────────────────┤
│ IDEA → STORY → OUTLINE → SCREENPLAY → REVIEW → LOCK│
├─────────────────────────────────────────────────────┤
│ Overview | Idea | Story | Outline | Screenplay ... │
├─────────────────────────────────────────────────────┤
│                                                     │
│                   Workspace content                 │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Tabs

```text
Overview
Idea
Story
Outline
Screenplay
Review
Revisions
Activity
```

`Approval` và `Lock` là actions/state, không nhất thiết cần tab riêng.

## UI5.1 Pipeline progress

Map server state vào visual pipeline.

Không frontend tự quyết định state.

Ví dụ:

```text
IDEATION              Idea active
STORY_DEVELOPMENT     Story active
OUTLINE_READY         Outline complete
SCREENPLAY_DRAFT      Screenplay active
SCREENPLAY_REVIEW     Review active
SCREENPLAY_APPROVAL   Approval waiting
SCREENPLAY_LOCKED     Locked
READY_FOR_PRODUCTION  Complete
```

## UI5.2 Overview

Tập hợp:

```text
episode metadata
current state
active revision
run status
last review
approval state
screenplay lock state
```

### Gate

```text
WIND_STUDIO_UI5_EPISODE_WORKSPACE_LIVE
```

---

# PHASE UI6 — IDEA & STORY UX

## Idea tab

Candidate card cần thể hiện:

```text
title
logline
premise
theme
genre
score dimensions
selected state
```

Actions chỉ expose khi server cho phép:

```text
Select
Regenerate
Resume Run
```

SelectedIdea phải có visual state rõ ràng.

## Story tab

Story không nên đổ tất cả JSON thành một panel.

Sub-navigation:

```text
Story Bible
World
Characters
Beat Sheet
```

### Story Bible

Sections:

```text
Premise
Theme
Core Conflict
Tone
Story Rules
Character Arcs
Constraints
```

### Character Canon

Card/list:

```text
name
role
motivation
personality
speech style
relationships
continuity rules
```

### Beat Sheet

Hiển thị timeline:

```text
Beat 01
purpose
conflict
turn
duration

↓
Beat 02
...
```

### Gate

```text
WIND_STUDIO_UI6_IDEA_STORY_EXPERIENCE_VERIFIED
```

---

# PHASE UI7 — OUTLINE & SCREENPLAY UX

## Outline

Scene-based presentation:

```text
Scene 01
INT. HOUSE — MORNING

Characters
Objective
Conflict
Turn
Duration
Story Value
```

Thêm:

```text
scene navigation
duration summary
character/location summary
```

chỉ nếu data đã có.

## Screenplay

Roadmap 1 cần screenplay đọc và review tốt trước tiên.

Target:

```text
Left rail
  Scene list

Center
  formatted screenplay

Right inspector
  revision
  duration
  continuity
  findings
```

Không lấy production-domain editor về dùng ngay chỉ vì nó tồn tại.

Trước khi reuse `production-ui StructuredEditor/TextEditor`, phải đánh giá:

```text
domain coupling
contract compatibility
revision semantics
dependencies
```

Nếu coupling cao:

```text
do not reuse
```

## Read-only rule

Khi:

```text
SCREENPLAY_LOCKED
READY_FOR_PRODUCTION
```

editor phải chuyển sang:

```text
READ ONLY
```

### Gate

```text
WIND_STUDIO_UI7_SCREENPLAY_WORKSPACE_VERIFIED
```

---

# PHASE UI8 — REVIEW, REVISION, APPROVAL & LOCK

## Review UX

Thay review report thô bằng:

```text
Overall Score

Dimensions
├── Plot
├── Character
├── Continuity
├── Pacing
├── Dialogue
├── Audience Fit
└── Production Feasibility

Findings
├── BLOCKING
├── MAJOR
├── MINOR
└── SUGGESTION
```

## Revision

Hiển thị:

```text
Revision v1 → v2

changed scenes
reason
findings addressed
screenplay diff
```

Không synthesize revision ở frontend.

## Approval

Nếu server báo:

```text
WAITING_FOR_APPROVAL
```

mới expose controls:

```text
Approve
Reject
Request Revision
```

## Lock

Lock phải là action có xác nhận rõ:

```text
revision
screenplay hash
review status
```

Sau lock:

```text
Locked badge
immutable warning
READY_FOR_PRODUCTION handoff
```

### Gate

```text
WIND_STUDIO_UI8_REVIEW_APPROVAL_LOCK_VERIFIED
```

---

# PHASE UI9 — RUNTIME STATUS & ACTIVITY UX

Có thể thực hiện song song UI6–UI8.

## Mục tiêu

Không để runtime diagnostics chi phối creative UI.

Top bar chỉ giữ:

```text
Backend
Worker/Studio capability
CPU
RAM
GPU
VRAM
```

Chi tiết runtime chuyển vào:

```text
System / Diagnostics
```

## Hermes

Hiện Hermes badge không có runtime thật.

Không tiếp tục hiển thị như một health indicator có ý nghĩa nếu vẫn hardcoded false.

Target tạm:

```text
remove from primary status strip
```

hoặc:

```text
Unavailable / Not configured
```

Không fake green state.

## Activity tab

Dùng server run/events nếu available:

```text
Idea generation started
Idea candidates generated
Idea selected
Story development completed
Review completed
Revision created
Screenplay locked
```

Không tạo fake timeline.

### Gate

```text
WIND_STUDIO_UI9_RUNTIME_VISIBILITY_TRUTHFUL
```

---

# PHASE UI10 — PRODUCTION ISOLATION + SYSTEM REGROUP

## Production

Roadmap 1 không redesign production video.

Target:

```text
PRODUCTION
    ▼ collapsed

Assets
Production Workspace
Renders
```

Có thể thêm label:

```text
Roadmap 2
Preview
Experimental
```

nếu phù hợp.

Không sửa:

```text
FakeProductionApiClient
production contracts
production state
asset pipeline
Blender UI
```

trong roadmap này.

## System pages

Regroup:

```text
Agent Workspace
Models
Router / Providers
Browser
Files
Settings
```

Các page stub/fake vẫn phải được phân loại đúng.

Không làm chúng trông như feature production-ready nếu backend chưa có.

### Gate

```text
WIND_STUDIO_UI10_PRODUCT_SURFACES_ISOLATED
```

---

# PHASE UI11 — DESKTOP POLISH

## Mục tiêu

Chuyển từ “functional UI” thành coherent desktop application.

Kiểm tra:

```text
1920×1080
1600×900
1440×900
1366×768
1200×800
```

Desktop không nhất thiết mobile responsive, nhưng phải hoạt động ở minimum Tauri window.

## Polish

Chuẩn hóa:

```text
spacing
font hierarchy
hover
focus
selected
disabled
loading
empty
error
offline
locked
running
waiting
success
```

## Accessibility

Tối thiểu:

```text
keyboard navigation
visible focus
button labels
form labels
semantic tabs
contrast
disabled semantics
```

## Performance

Kiểm tra bundle.

Hiện frontend single chunk khá lớn; redesign không được làm bundle tăng vô kiểm soát.

Có thể áp dụng lazy loading cho:

```text
System pages
Production
heavy workspace
```

nếu có bằng chứng cần thiết.

### Gate

```text
WIND_STUDIO_UI11_DESKTOP_POLISH_VERIFIED
```

---

# PHASE UI12 — REAL DESKTOP CERTIFICATION

Đây là phase quyết định.

## Test scenario

Không test bằng fake Studio client.

Input:

```text
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
Develop Story
    ↓
Generate Outline
    ↓
Generate Screenplay
    ↓
Review
    ↓
Revision
    ↓
Approval
    ↓
Lock
```

Kết quả cuối:

```text
READY_FOR_PRODUCTION
```

## Runtime path bắt buộc

```text
Tauri Desktop
  ↓
React UI
  ↓
StudioStore
  ↓
HttpStudioApiClient
  ↓
API V3
  ↓
OrchestratorService
  ↓
Worker
  ↓
Provider
  ↓
Persistence
```

Không được:

```text
FakeStudioClient
manual DB insertion
direct Story handler invocation
frontend-generated artifacts
hardcoded success
skip worker
```

---

# 4. Test strategy xuyên suốt

Mỗi phase phải chạy ít nhất:

```text
desktop typecheck
desktop vitest
studio package tests
desktop build
web build
```

Các phase ảnh hưởng Studio phải chạy thêm:

```text
Studio shell tests
Studio story tests
deep-link tests
approval tests
lock tests
run polling tests
contract drift tests
```

Trước UI12:

```text
full Python regression
frontend full tests
Desktop full tests
API V3 contract
architecture checker
version checker
artifact validator
```

Không sửa failing test ngoài root cause của phase.

---

# 5. Artifact structure

Mỗi phase tạo evidence:

```text
artifacts/studio_refactor/roadmap_01/desktop_redesign/

ui0/
ui1/
ui2/
...
ui12/
```

Mỗi phase tối thiểu:

```text
phase_summary.md
change_manifest.json
test_matrix.json
build_report.json
risk_report.json
verdict.json
```

Nếu có screenshot regression:

```text
screenshots/
```

không cần commit ảnh lớn nếu evidence policy không cho phép.

---

# 6. Architecture guardrails

Nên bổ sung architecture test đảm bảo:

```text
story-ui
    X MUST NOT import HttpStudioApiClient

story-ui
    X MUST NOT instantiate StudioStore

studio-shell
    X MUST NOT import backend implementation

apps/desktop
    MAY compose story-ui + studio-state

production-ui
    MUST remain isolated from story-ui
```

Target dependency:

```text
studio-contracts
       ↑
studio-client
       ↑
studio-state
       ↑
apps/desktop composition

story-ui
       ↑
apps/desktop composition

studio-shell
       ↑
apps/desktop composition
```

`story-ui` và `studio-shell` không trở thành business/runtime authorities.

---

# 7. Phần nào chạy song song được

```text
UI0
 ↓
UI1
 ↓
UI2
 ↓
UI3
 ├──────────────────────┐
 ↓                      ↓
UI4A story-ui        UI4B Studio/Series
 └───────────┬──────────┘
             ↓
            UI5
     ┌───────┼───────────┐
     ↓       ↓           ↓
    UI6     UI9         UI10
     ↓
    UI7
     ↓
    UI8
     └────────┬───────────┘
              ↓
             UI11
              ↓
             UI12
```

Critical path:

```text
UI0
→ UI1
→ UI2
→ UI3
→ UI4A
→ UI5
→ UI6
→ UI7
→ UI8
→ UI11
→ UI12
```

---

# 8. Files có blast radius cao nhất

Theo inventory hiện tại, thứ tự ưu tiên xử lý nên là:

```text
1. apps/desktop/src/App.tsx
2. apps/desktop/src/styles.css
3. apps/desktop/src/pages/StudioPage.tsx
4. apps/desktop/src/components/studio/ArtifactViews.tsx
5. apps/desktop/src/components/studio/RunProgress.tsx
6. apps/desktop/src/components/studio/ApprovalBar.tsx
7. frontend/packages/story-ui/            NEW
8. frontend/packages/studio-shell/        NEW
9. Desktop Studio tests
10. apps/web integration/re-export
```

`App.tsx` và `StudioPage.tsx` tuyệt đối không nên bị rewrite đồng thời trong một commit lớn.

---

# 9. Commit strategy

Tôi đề xuất commit nhỏ theo kiến trúc:

```text
Commit 1
UI0 evidence only

Commit 2
design tokens/primitives

Commit 3
extract TopBar

Commit 4
extract Sidebar

Commit 5
extract AppShell

Commit 6
data-driven navigation

Commit 7
create story-ui + pure moves

Commit 8
Studio Home

Commit 9
Series Detail

Commit 10
Episode Workspace shell

Commit 11
Idea UX

Commit 12
Story UX

Commit 13
Outline UX

Commit 14
Screenplay UX

Commit 15
Review/revision UX

Commit 16
Approval/lock UX

Commit 17
runtime/activity truthfulness

Commit 18
Production/System regroup

Commit 19
polish/accessibility

Commit 20
certification evidence
```

Tránh commit kiểu:

```text
"redesign entire desktop"
```

vì khi regression xảy ra sẽ rất khó phân biệt lỗi presentation, store, routing hay runtime.

---

# 10. Definition of Done

Desktop redesign chỉ hoàn thành khi người dùng có thể:

1. Mở WindAgent Studio.
2. Nhìn thấy Studio là product surface chính.
3. Tạo Series.
4. Mở Series và quản lý Episodes.
5. Vào một Episode Workspace.
6. Xem trạng thái toàn pipeline.
7. Generate/chọn Idea.
8. Xem Story Bible, World Bible, Character Canon, Beat Sheet.
9. Xem Outline theo scene.
10. Generate và đọc Screenplay.
11. Xem Review theo severity/dimension.
12. Xem revision/diff.
13. Approve hoặc request revision.
14. Lock screenplay.
15. Nhìn thấy trạng thái:

```text
READY_FOR_PRODUCTION
```

Và đồng thời:

```text
Studio V3 contract unchanged
StudioStore remains server-authority
no Fake Studio runtime
Production preserved
Tauri shell still works
Desktop tests PASS
Web build PASS
Desktop build PASS
real vertical slice PASS
```

Final UI verdict:

```text
WIND_STUDIO_DESKTOP_ROADMAP_1_UI_CERTIFIED
```

Bản kế hoạch này cố tình ưu tiên **tách shell → tách story presentation → dựng Episode Workspace → redesign từng workflow surface**, thay vì chỉnh giao diện trực tiếp trên `App.tsx` và `StudioPage.tsx`. Với kiến trúc hiện tại, đó là con đường có blast radius thấp nhất và tận dụng được phần Studio runtime đã tồn tại thay vì viết lại nó. 
