# Roadmap tổng thể

Kiến trúc mục tiêu:

```text
VideoClaw-derived Pre-production
             │
             ▼
VideoProductionPackage v1
             │
             ▼
WindAgent Director & Production Layer
             │
             ▼
Google Flow Browser Generation Provider
             │
             ▼
Audio / Post-production / Verification
```

Phân quyền:

```text
VideoClaw-derived modules
    = ý tưởng, nghiên cứu, screenplay, nhân vật, bối cảnh, asset đầu vào

wind_agent
    = nguồn sự thật, đạo diễn, shot planning, continuity,
      scheduling, approval, cost, retry, recovery, verification

Google Flow
    = tạo/chỉnh sửa ảnh và video qua giao diện trình duyệt

ViMax
    = tài liệu tham khảo hành vi và kiến trúc
      KHÔNG phải dependency và KHÔNG sao chép source/prompt
```

Cách phân chia này phù hợp với Architecture V2 hiện tại của `WindAgent`: `intelligence` chịu trách nhiệm planner/reviewer, `tools` chứa browser và tool integrations, `workflows` chứa workflow definitions, còn `storage`, `observability` và `verification` đã có vị trí kiến trúc riêng.

VideoClaw hiện là pipeline end-to-end gồm script, nhân vật/bối cảnh, storyboard, ảnh tham chiếu, video và hậu kỳ. Vì vậy cần **cắt bỏ quyền điều phối cuối** của VideoClaw, không đưa nguyên monolith vào runtime của WindAgent. ([GitHub][1])

---

# Kiến trúc package mục tiêu

Không nên tạo một package monolith mới như `video_system/`. Nên mở rộng các package canonical hiện có.

```text
wind-agent/
├── core/
│   └── windagent_core/
│       ├── domain/
│       │   └── video_production/
│       │       ├── project.py
│       │       ├── screenplay.py
│       │       ├── character.py
│       │       ├── location.py
│       │       ├── scene.py
│       │       ├── shot.py
│       │       ├── asset.py
│       │       ├── continuity.py
│       │       ├── generation_job.py
│       │       └── approval.py
│       ├── contracts/
│       │   └── video_production/
│       │       ├── preproduction.py
│       │       ├── direction.py
│       │       ├── media_generation.py
│       │       ├── asset_storage.py
│       │       └── quality_review.py
│       └── events/
│           └── video_production.py
│
├── intelligence/
│   └── windagent_intelligence/
│       └── video/
│           ├── ideation/
│           ├── screenplay/
│           ├── director/
│           ├── shot_planner/
│           ├── continuity/
│           ├── reference_selector/
│           ├── prompt_compiler/
│           └── reviewers/
│
├── tools/
│   └── windagent_tools/
│       ├── video_preproduction/
│       ├── media_assets/
│       ├── browser/
│       ├── google_flow/
│       ├── ffmpeg/
│       └── ffprobe/
│
├── workflows/
│   └── windagent_workflows/
│       └── video_production/
│           ├── idea_to_package.py
│           ├── package_to_shot_plan.py
│           ├── render_sequence.py
│           ├── postproduction.py
│           └── full_production.py
│
├── orchestration/
│   └── windagent_orchestration/
│       └── production/
│           ├── dependency_graph.py
│           ├── scheduler.py
│           ├── invalidation.py
│           └── recovery.py
│
├── storage/
│   └── windagent_storage/
│       └── video_production/
│
├── verification/
│   └── windagent_verification/
│       └── media/
│
├── observability/
│   └── windagent_observability/
│       └── media_generation/
│
└── third_party/
    └── videoclaw/
        ├── upstream/
        ├── PATCHES.md
        ├── UPSTREAM_MANIFEST.json
        ├── LICENSE
        └── NOTICE.md
```

## Vị trí của Google Flow Browser Provider

Về mặt khái niệm, nó là một `GenerationProvider`. Nhưng implementation nên nằm trong `tools/google_flow`, vì nó phụ thuộc browser runtime.

```text
core:
    MediaGenerationProviderPort

tools/google_flow:
    GoogleFlowBrowserGenerationProvider

providers:
    GoogleVeoApiProvider
    KlingApiProvider
    SeedanceApiProvider
```

Như vậy không phải sửa `providers` để phụ thuộc vào browser tool, đồng thời vẫn giữ được một interface thống nhất:

```python
class MediaGenerationProviderPort(Protocol):
    async def generate_image(...): ...
    async def generate_video(...): ...
    async def extend_video(...): ...
    async def inspect_job(...): ...
    async def download_result(...): ...
```

---

# Milestone A — Baseline, governance và upstream intake

## Phase 0 — Freeze baseline và mở program mới

### Mục tiêu

Tách chương trình video production khỏi Phase 7 hiện tại và không làm hỏng baseline đã được chứng nhận.

Commit `cbf725...` là commit attestation Phase 7, tham chiếu `verified_sha`, evidence bundle và trạng thái `verified_remote_and_local`.

### Công việc

1. Xác nhận commit khởi đầu:

```text
cbf7257643d4a1705fa221ae37e9391b6ee3f40e
```

2. Tạo branch chương trình:

```text
feat/video-production-platform
```

3. Chạy lại baseline:

```text
architecture checker
full pytest
CLI verification
web tests
desktop tests
build checks
```

4. Tạo thư mục evidence:

```text
artifacts/video_production/phase_00/
├── baseline_commit.json
├── workspace_inventory.json
├── test_baseline.json
├── architecture_baseline.json
└── baseline_verdict.json
```

5. Không thêm VideoClaw vào workspace trong phase này.

### Gate

```text
VP0_BASELINE_FROZEN
```

* Worktree sạch.
* Không regression so với commit gốc.
* Không thay đổi runtime.
* Mọi phase sau đều tham chiếu baseline SHA này.

---

## Phase 1 — Upstream legal, security và provenance review

### Mục tiêu

Xác định chính xác phần nào của VideoClaw được dùng, phần nào bị loại và nghĩa vụ giấy phép.

VideoClaw dùng MIT License, cho phép sử dụng và sửa đổi nhưng yêu cầu giữ copyright và permission notice trong các bản sao hoặc phần đáng kể.

### Công việc

1. Pin một commit VideoClaw cụ thể, không dùng floating `main`.
2. Tạo:

```text
docs/upstream/videoclaw/
├── source_commit.md
├── license_review.md
├── dependency_inventory.md
├── security_inventory.md
├── feature_inventory.md
└── adoption_matrix.md
```

3. Phân loại source:

```text
ADOPT_AND_REFACTOR
REWRITE_FOR_WINDAGENT
REFERENCE_ONLY
REJECT
UNKNOWN
```

4. Kiểm kê:

* Python dependencies.
* Node dependencies.
* FFmpeg binaries.
* Model/provider SDK.
* File download logic.
* Secret handling.
* Network/proxy configuration.
* Local artifact storage.
* Dynamic imports.
* Subprocess execution.
* Frontend coupling.
* Provider fallback.
* Tests và fixtures.

5. Xác minh không có:

* Secret trong repo.
* Binary không rõ nguồn.
* Model weight không rõ license.
* Dịch vụ hard-coded.
* Telemetry không được khai báo.
* Dependency có license không tương thích.

### Gate

```text
VP1_UPSTREAM_ADOPTION_APPROVED
```

---

## Phase 2 — Clean-room specification từ ViMax

### Mục tiêu

Tham khảo ViMax nhưng thiết kế và triển khai độc lập.

ViMax có những capability hữu ích để nghiên cứu: tách screenplay thành storyboard và shot, quản lý reference, camera continuity, render checkpoints, resume và parallel generation. ([GitHub][2])

`Script2VideoPipeline` hiện tách được text planning khỏi rendering, tạo storyboard, shot descriptions và camera tree trước khi render. Đây là hành vi có thể học, nhưng không nên port source hoặc prompt. ([GitHub][3])

### Quy tắc clean-room

Không sao chép:

* Source code.
* Prompt nguyên văn.
* Class hierarchy.
* Schema nội bộ.
* Tên private method.
* Test fixture.
* Comment hoặc tài liệu dài.

Chỉ trích xuất:

* Vấn đề cần giải quyết.
* Input/output kỳ vọng.
* Invariant.
* Failure mode.
* Acceptance behavior.

### Tài liệu cần tạo

```text
docs/video_production/director_research/
├── vimax_behavior_inventory.md
├── independent_requirements.md
├── terminology_mapping.md
├── rejected_designs.md
└── clean_room_attestation.md
```

### Đổi terminology

| Khái niệm tham khảo         | Thiết kế WindAgent           |
| --------------------------- | ---------------------------- |
| Camera tree                 | `ShotDependencyGraph`        |
| Storyboard artist           | `CinematicPlanner`           |
| Character portrait registry | `IdentityReferenceCatalog`   |
| Reference image selector    | `ReferenceBindingPlanner`    |
| Script2Video pipeline       | `ProductionPlanningWorkflow` |
| Working directory cache     | `ArtifactRevisionStore`      |

### Gate

```text
VP2_DIRECTOR_REQUIREMENTS_FROZEN
```

---

## Phase 3 — Canonical Video Production Protocol

### Mục tiêu

Tạo schema trung gian làm source of truth giữa VideoClaw-derived pre-production, Director Layer và Flow.

### Domain model chính

```text
VideoProject
ProductionRevision
CreativeBrief
StoryConcept
Screenplay
Scene
CharacterBible
LocationBible
PropBible
StyleBible
DialogueLine
CinematicPlan
Shot
ShotDependency
ContinuityState
ReferenceAsset
GenerationRequest
GenerationCandidate
ReviewResult
ApprovalDecision
FinalDeliverable
```

### Artifact trung tâm

```text
VideoProductionPackage v1
```

Ví dụ cấu trúc:

```json
{
  "schema_version": "1.0.0",
  "project_id": "vp_01",
  "revision_id": "rev_03",
  "creative_brief": {},
  "screenplay": {
    "scenes": []
  },
  "characters": [],
  "locations": [],
  "props": [],
  "style_bible": {},
  "dialogue": [],
  "production_constraints": {},
  "assets": [],
  "provenance": {},
  "approval_state": {}
}
```

### Invariant bắt buộc

* ID ổn định, không dùng tên nhân vật làm khóa.
* Scene và shot có thứ tự xác định.
* Asset luôn có hash.
* Asset tải từ internet có provenance.
* Mọi revision immutable.
* Thay đổi screenplay tạo revision mới.
* Không sửa artifact đã được khóa.
* Mọi generated output truy ngược được về prompt và reference.

### Event protocol

```text
VideoProjectCreated
ConceptApproved
ScreenplayGenerated
ScreenplayLocked
CharacterBibleApproved
LocationBibleApproved
CinematicPlanGenerated
ShotPlanLocked
GenerationSubmitted
GenerationCompleted
GenerationRejected
HumanActionRequired
SequenceCompleted
FinalVideoPublished
```

### Gate

```text
VP3_CANONICAL_PROTOCOL_VERIFIED
```

---

# Milestone B — VideoClaw intake và tái cấu trúc

## Phase 4 — Tải và quarantine VideoClaw upstream

### Mục tiêu

Đưa source VideoClaw về repo để phân tích nhưng chưa cho phép nó trở thành runtime authority.

VideoClaw hiện có backend Python, frontend Node và lưu metadata/artifact vào các thư mục JSON/local filesystem riêng. ([GitHub][1]) ([GitHub][1])

### Cách nhập source

```text
third_party/videoclaw/upstream/
```

Không đưa vào:

```toml
[tool.uv.workspace].members
```

Không thêm vào Python path.

### Manifest

```json
{
  "source_repository": "HITsz-TMG/VideoClaw",
  "source_commit": "<PINNED_SHA>",
  "license": "MIT",
  "imported_at": "...",
  "content_sha256": "...",
  "patch_policy": "NO_DIRECT_RUNTIME_IMPORT"
}
```

### Architecture rules

* Canonical package không import `third_party`.
* `third_party` không được dùng làm composition root.
* Không chạy upstream API server trong production.
* Không dùng upstream frontend.
* Không dùng upstream config làm source of truth.
* Không commit API key.
* Architecture checker fail nếu canonical package import upstream path.

### Gate

```text
VP4_VIDEOCLAW_QUARANTINED
```

---

## Phase 5 — Characterization testing của VideoClaw

### Mục tiêu

Hiểu chính xác hành vi trước khi refactor.

### Test matrix

1. Idea → concept.
2. Concept → screenplay.
3. Screenplay → character extraction.
4. Screenplay → setting extraction.
5. Character → image prompt.
6. Setting → image prompt.
7. Story continuation.
8. Script revision.
9. Asset replacement.
10. Error handling khi thiếu model.
11. Artifact path và naming.
12. Resume sau crash.
13. Không có network.
14. Provider timeout.
15. Invalid image.
16. Duplicate session ID.

### Golden fixture

Tạo ba fixture:

```text
fixture_short_cartoon
fixture_two_character_dialogue
fixture_multi_scene_drama
```

Output được canonicalize trước khi snapshot để loại bỏ:

* Timestamp.
* Random ID.
* Absolute path.
* Model metadata không ổn định.

### Kết quả

```text
artifacts/video_production/phase_05/
├── behavior_matrix.json
├── golden_outputs/
├── defect_inventory.json
├── nondeterminism_inventory.json
└── phase_verdict.json
```

### Gate

```text
VP5_VIDEOCLAW_BEHAVIOR_CHARACTERIZED
```

---

## Phase 6 — Tách Pre-production Kernel khỏi VideoClaw

### Mục tiêu

Trích các khả năng cần thiết khỏi monolith và viết lại theo Architecture V2.

### Phần giữ lại

* Idea expansion.
* Creative brief generation.
* Story outline.
* Multi-scene screenplay.
* Dialogue and narration.
* Character extraction.
* Location extraction.
* Prop extraction.
* Style definition.
* Plot continuation.
* Asset prompt generation.
* Asset acquisition.

### Phần loại khỏi kernel

* Video generation provider.
* Final video editing.
* Upstream project/session authority.
* Local JSON task database.
* Upstream WebUI.
* Upstream provider config.
* Upstream orchestration.
* Upstream storyboard authority.

### Module mới

```text
intelligence/video/ideation/
intelligence/video/screenplay/
intelligence/video/entity_extraction/
intelligence/video/style_design/
tools/video_preproduction/
```

### Refactor strategy

Không di chuyển tất cả file cùng lúc.

```text
characterize
    ↓
extract one capability
    ↓
implement canonical contract
    ↓
compare outputs
    ↓
remove dependency on upstream implementation
```

### Gate

```text
VP6_PREPRODUCTION_KERNEL_CANONICAL
```

* Không import `third_party`.
* Golden behavior đạt ngưỡng tương đương.
* Output hợp lệ theo `VideoProductionPackage`.
* Có provider-agnostic LLM/VLM contracts.
* Có unit test và integration test.

---

## Phase 7 — Asset acquisition và provenance

### Mục tiêu

Cho phép tạo ảnh bằng model hoặc tải ảnh hợp pháp từ internet.

### Thành phần

```text
AssetSearchService
AssetDownloadService
AssetValidationService
AssetProvenanceService
IdentityReferenceBuilder
LocationReferenceBuilder
```

### Bảo mật downloader

* Chỉ HTTP/HTTPS.
* Chặn localhost/private IP.
* Redirect revalidation.
* MIME sniffing.
* Giới hạn dung lượng.
* Pixel/decompression limit.
* Không nhận executable.
* SVG sanitization hoặc cấm SVG.
* Hash và duplicate detection.
* Malware scanning khi có thể.
* Xóa EXIF nhạy cảm.
* License metadata.
* Human approval cho likeness người thật.

### Asset lifecycle

```text
DISCOVERED
DOWNLOADED
VALIDATED
LICENSE_UNKNOWN
APPROVED
REJECTED
BOUND_TO_PROJECT
```

### Gate

```text
VP7_ASSET_PIPELINE_VERIFIED
```

---

# Milestone C — WindAgent Director Layer

## Phase 8 — Director Layer foundation

### Mục tiêu

Biến screenplay thành kế hoạch quay độc lập với provider.

### Service chính

```python
class VideoDirectorService:
    async def create_cinematic_plan(
        self,
        package: VideoProductionPackage,
    ) -> CinematicPlan:
        ...
```

### Responsibilities

* Phân tích mục tiêu scene.
* Xác định nhịp kể.
* Chia scene thành shot.
* Chọn shot size.
* Chọn camera angle.
* Chọn camera movement.
* Tính duration.
* Gắn dialogue vào shot.
* Xác định reference cần thiết.
* Xác định generation mode.
* Kiểm tra giới hạn tổng thời lượng.

### Không cho phép

* Tự thay đổi screenplay đã khóa.
* Tự thêm nhân vật chính.
* Tự đổi bối cảnh.
* Tự sửa lời thoại mà không có proposal.
* Tự submit generation.

### Script revision protocol

```text
DirectorialIssue
    ↓
ScriptRevisionProposal
    ↓
Approval gate
    ↓
new screenplay revision
```

### Gate

```text
VP8_DIRECTOR_FOUNDATION_VERIFIED
```

---

## Phase 9 — Shot Dependency Graph và camera planning

### Mục tiêu

Viết lại các ý tưởng continuity/camera dependency theo thiết kế riêng.

### Model

```text
ShotDependencyGraph
├── temporal_dependency
├── visual_reference_dependency
├── continuity_dependency
├── transition_dependency
├── dialogue_dependency
└── asset_dependency
```

### Các loại shot

```text
ESTABLISHING
MASTER
MEDIUM
CLOSE_UP
EXTREME_CLOSE_UP
OVER_SHOULDER
POV
INSERT
REACTION
TRANSITION
```

### Generation mode decision

```text
TEXT_TO_VIDEO
IMAGE_TO_VIDEO
FRAMES_TO_VIDEO
INGREDIENTS_TO_VIDEO
VIDEO_EXTENSION
VIDEO_TO_VIDEO
```

Flow hiện chính thức hỗ trợ text-to-video, frames-to-video, ingredients-to-video, video extension cùng các công cụ tạo ảnh/video và quản lý character. ([Google Labs][4])

### Scheduling rule

* Shot không phụ thuộc có thể chạy song song.
* Shot dùng tail frame phải chờ predecessor.
* Reaction shot có thể dùng chung identity reference.
* Transition shot phải chờ hai endpoint frame.
* Một sequence có thể retry độc lập.

### Gate

```text
VP9_SHOT_GRAPH_AND_CAMERA_PLAN_VERIFIED
```

---

## Phase 10 — Continuity Ledger

### Mục tiêu

Theo dõi trạng thái điện ảnh xuyên shot và scene.

### Theo dõi

* Identity.
* Tuổi biểu kiến.
* Tóc.
* Trang phục.
* Vết thương.
* Emotion.
* Vị trí khung hình.
* Hướng nhìn.
* Đạo cụ đang giữ.
* Vị trí đạo cụ.
* Ánh sáng.
* Thời tiết.
* Thời gian.
* Trạng thái cửa/xe/phòng.
* Camera side.
* 180-degree rule.
* Scene geography.

### Model

```json
{
  "shot_id": "shot_010",
  "character_states": {},
  "location_state": {},
  "prop_states": {},
  "camera_state": {},
  "must_preserve": [],
  "allowed_changes": []
}
```

### Gate

```text
VP10_CONTINUITY_LEDGER_VERIFIED
```

---

## Phase 11 — Reference Binding và Prompt Compiler

### Mục tiêu

Chuyển shot plan thành request rõ ràng cho Flow.

### Pipeline

```text
ShotSpecification
    ↓
ReferenceBindingPlanner
    ↓
FlowGenerationSpecification
    ↓
PromptCompiler
    ↓
GenerationRequest
```

### Prompt block

```text
PROJECT STYLE
IDENTITY
LOCATION
PROPS
SHOT COMPOSITION
ACTION
CAMERA
LIGHTING
CONTINUITY
DIALOGUE/AUDIO INTENT
DURATION
NEGATIVE CONSTRAINTS
```

### Yêu cầu

* Prompt versioned.
* Prompt hash.
* Reference hash.
* Không chứa path nhạy cảm.
* Không chứa instruction từ metadata tải trên mạng.
* Có token/length limit.
* Có compiler riêng theo generation mode.
* Không để LLM nhập trực tiếp vào browser.

### Gate

```text
VP11_FLOW_REQUEST_COMPILER_VERIFIED
```

---

# Milestone D — Google Flow Browser Provider

## Phase 12 — Browser runtime foundation

### Mục tiêu

Tạo browser worker có session bền vững nhưng chưa thao tác Flow production.

### Runtime đề xuất

```text
agent-browser
    +
headed Chrome/Chromium
    +
persistent local profile
    +
WindAgent bounded execution wrapper
```

`agent-browser` cung cấp accessibility snapshot, persistent state, screenshot, domain filtering, action policies và confirmation gates; đây là những khả năng phù hợp để làm browser runtime có kiểm soát. ([GitHub][5]) ([GitHub][6])

### Module

```text
tools/browser/
├── runtime.py
├── session.py
├── command_runner.py
├── snapshot_parser.py
├── action_policy.py
├── evidence_capture.py
└── healthcheck.py
```

### Yêu cầu

* Pin version `agent-browser`.
* Timeout mọi command.
* Kill process tree khi cancel.
* Một session ID tương ứng một Chrome profile.
* Domain allowlist.
* Không cho tùy ý `eval`.
* Không xuất cookie vào log.
* Không truyền profile qua message queue.
* Browser worker không có quyền Git/file system rộng.

### Gate

```text
VP12_BROWSER_RUNTIME_VERIFIED
```

---

## Phase 13 — Flow navigation và project management

### Mục tiêu

Tự động hóa navigation deterministic trước khi submit generation.

### Luồng hỗ trợ

1. Mở Flow.
2. Kiểm tra account/session.
3. Mở hoặc tạo project.
4. Xác nhận đúng project.
5. Mở create workspace.
6. Chọn generation mode.
7. Upload references.
8. Điền prompt.
9. Chọn model/duration/aspect ratio.
10. Chụp evidence trước submit.

### Selector strategy

Ưu tiên:

```text
accessibility role
label
visible text
stable URL
semantic region
```

Không phụ thuộc chính vào:

```text
generated CSS class
DOM index
screen coordinate
```

### UI state machine

```text
UNKNOWN
SIGNED_OUT
READY
PROJECT_OPEN
EDITOR_READY
CONFIGURED
SUBMIT_READY
GENERATING
RESULT_READY
ERROR
HUMAN_ACTION_REQUIRED
```

### Gate

```text
VP13_FLOW_NAVIGATION_VERIFIED
```

---

## Phase 14 — Image generation qua Flow

### Mục tiêu

Hỗ trợ ảnh nhân vật, location, props, first frame và last frame.

### Operations

```text
CREATE_CHARACTER_REFERENCE
CREATE_LOCATION_REFERENCE
CREATE_PROP_REFERENCE
CREATE_STORYBOARD_FRAME
CREATE_FIRST_FRAME
CREATE_LAST_FRAME
EDIT_IMAGE
UPSCALE_IMAGE
```

### Candidate handling

* Không mặc định chọn candidate đầu tiên.
* Download từng candidate.
* Lưu request và screenshot.
* Kiểm tra kích thước/file validity.
* VLM chấm identity và prompt compliance.
* Human approval cho character master.

### Gate

```text
VP14_FLOW_IMAGE_GENERATION_VERIFIED
```

---

## Phase 15 — Video generation qua Flow

### Mục tiêu

Tạo clip theo shot plan.

### Operations

```text
TEXT_TO_VIDEO
FRAMES_TO_VIDEO
INGREDIENTS_TO_VIDEO
VIDEO_EXTENSION
VIDEO_TO_VIDEO
```

### Job record

```json
{
  "generation_id": "...",
  "project_id": "...",
  "shot_id": "...",
  "provider": "google_flow_browser",
  "request_hash": "...",
  "submitted_at": "...",
  "browser_session_id": "...",
  "flow_project_id": "...",
  "status": "GENERATING",
  "attempt": 1
}
```

### Idempotency

Trước khi submit:

```text
lookup request_hash
    ├── completed → reuse artifact
    ├── generating → resume inspection
    ├── failed retryable → retry
    └── missing → submit
```

### Gate

```text
VP15_FLOW_VIDEO_GENERATION_VERIFIED
```

---

## Phase 16 — Human intervention và account safety

### Mục tiêu

Xử lý login, CAPTCHA, verification và payment một cách an toàn.

### Trạng thái

```text
HUMAN_LOGIN_REQUIRED
HUMAN_CAPTCHA_REQUIRED
HUMAN_ACCOUNT_VERIFICATION_REQUIRED
HUMAN_TERMS_ACCEPTANCE_REQUIRED
HUMAN_PAYMENT_CONFIRMATION_REQUIRED
```

### Quy tắc bắt buộc

Không triển khai:

* CAPTCHA bypass.
* Fingerprint spoofing.
* Proxy rotation để né rate limit.
* Account rotation để vượt quota.
* Tự xác nhận thanh toán.
* Tự vượt account challenge.
* Retry vô hạn sau khi bị chặn.

Chỉ triển khai:

* Persistent legitimate session.
* Headed browser.
* Backoff.
* Human takeover.
* Resume sau khi người dùng xử lý.
* Screenshot evidence.
* Session health check.
* Rate/concurrency limit.

### Gate

```text
VP16_FLOW_HUMAN_CONTROL_VERIFIED
```

---

# Milestone E — Production orchestration

## Phase 17 — Durable production workflow

### Mục tiêu

Ghép toàn bộ capability thành workflow có thể pause, resume và recover.

### Workflow

```text
CREATE_PROJECT
    ↓
GENERATE_CONCEPTS
    ↓
SELECT_CONCEPT
    ↓
GENERATE_SCREENPLAY
    ↓
LOCK_SCREENPLAY
    ↓
BUILD_CHARACTER_AND_LOCATION_BIBLES
    ↓
APPROVE_REFERENCES
    ↓
CREATE_CINEMATIC_PLAN
    ↓
LOCK_SHOT_PLAN
    ↓
ESTIMATE_COST
    ↓
RENDER_ASSETS
    ↓
RENDER_SHOTS
    ↓
REVIEW_CANDIDATES
    ↓
POST_PRODUCTION
    ↓
FINAL_VERIFICATION
    ↓
PUBLISH
```

### Approval gates

```text
CONCEPT_APPROVAL
SCREENPLAY_APPROVAL
CHARACTER_APPROVAL
LOCATION_APPROVAL
SHOT_PLAN_APPROVAL
COST_APPROVAL
FINAL_CUT_APPROVAL
```

### Recovery

* Worker chết sau submit.
* Browser đóng.
* Download thất bại.
* Flow project mất context.
* Một shot fail.
* Một sequence fail.
* Prompt revision.
* Reference replacement.
* User cancel.
* User archive project.

### Gate

```text
VP17_DURABLE_WORKFLOW_VERIFIED
```

---

## Phase 18 — Content-addressed artifact storage và invalidation

### Mục tiêu

Không lặp lại kiểu cache `file exists`.

ViMax hiện có nhiều nhánh skip dựa trên file đã tồn tại, ví dụ character registry, frame hoặc final video. Cách này hữu ích cho demo nhưng không đủ để xác định artifact có còn hợp lệ sau khi input thay đổi hay không. ([GitHub][3])

### Artifact key

```text
SHA256(
    canonical_input
    + prompt_version
    + reference_hashes
    + model
    + generation_mode
    + generation_parameters
)
```

### Invalidation graph

```text
screenplay changed
    → cinematic plan invalid
    → shot plan invalid
    → prompt invalid
    → frames invalid
    → clips invalid
    → final cut invalid

character reference changed
    → only dependent shots invalid

BGM changed
    → video clips remain valid
    → audio mix and final cut invalid
```

### Gate

```text
VP18_ARTIFACT_INVALIDATION_VERIFIED
```

---

## Phase 19 — Cost, credits và quota management

### Mục tiêu

Ngăn mất credits do retry hoặc candidate explosion.

Google AI Pro hiện cấp 1.000 Flow credits hàng tháng; credit cost là theo generation chứ không nhất thiết theo một thao tác/request, và một request có thể tạo nhiều output. Chi phí cũng thay đổi theo model và thời lượng. ([Trung tâm hỗ trợ Google][7])

### Thành phần

```text
CreditEstimator
GenerationBudgetPolicy
QuotaLedger
RetryBudget
Daily/Monthly Limit
ProviderCircuitBreaker
```

### Gate trước render

```json
{
  "estimated_credits": 280,
  "maximum_credits": 400,
  "candidate_count": 2,
  "retry_reserve": 80,
  "requires_approval": true
}
```

### Chính sách

* Không submit nếu credit state không xác định.
* Không retry nếu vượt budget.
* Quality mode phải được phê duyệt.
* Candidate count có giới hạn.
* Không submit song song nhiều generation trong PoC.
* Record observed credit trước/sau khi có thể.

### Gate

```text
VP19_COST_AND_QUOTA_CONTROL_VERIFIED
```

---

## Phase 20 — Candidate review và quality gates

### Mục tiêu

Tự động chọn candidate nhưng không che giấu lỗi.

### Review dimensions

```text
technical_validity
prompt_compliance
identity_consistency
location_consistency
prop_consistency
continuity
motion_quality
camera_compliance
dialogue_alignment
visual_artifacts
safety
```

### Reviewer hierarchy

```text
ffprobe / deterministic checks
        ↓
VLM scoring
        ↓
cross-shot comparison
        ↓
human review khi confidence thấp
```

### Không dùng một score duy nhất

```json
{
  "identity": 0.91,
  "continuity": 0.74,
  "motion": 0.85,
  "technical": true,
  "blocking_defects": [
    "prop changes hands"
  ],
  "verdict": "REJECT"
}
```

### Gate

```text
VP20_GENERATION_REVIEW_VERIFIED
```

---

# Milestone F — Audio, hậu kỳ và giao diện

## Phase 21 — Dialogue, TTS và audio production

### Mục tiêu

Tách audio khỏi Flow video generation để giữ lời thoại chính xác.

### Pipeline

```text
DialogueLine
    ↓
Voice casting
    ↓
TTS
    ↓
Forced alignment
    ↓
Shot timing adjustment
    ↓
Optional lip-sync
    ↓
SFX
    ↓
BGM
    ↓
Mixing and normalization
```

### Model

```text
CharacterVoiceProfile
DialogueTrack
WordTimestamp
SoundEffectCue
MusicCue
AudioMixPlan
```

### Gate

```text
VP21_AUDIO_PIPELINE_VERIFIED
```

---

## Phase 22 — FFmpeg post-production

### Mục tiêu

Xuất final video reproducibly.

### Chức năng

* Concatenate shots.
* Transition.
* Audio replacement/mixing.
* Subtitle.
* Aspect ratio conversion.
* Loudness normalization.
* Thumbnail.
* Metadata.
* Final encoding.
* Proxy preview.

### Verification

* `ffprobe`.
* Duration.
* Codec.
* Audio stream.
* Resolution.
* Frame rate.
* No black/truncated ending.
* Decode sample frames.
* SHA-256.

### Gate

```text
VP22_POST_PRODUCTION_VERIFIED
```

---

## Phase 23 — Web/Desktop production workspace

### Mục tiêu

Cho người dùng quan sát và can thiệp vào workflow.

### Màn hình

```text
Projects
Creative Brief
Screenplay Editor
Character Bible
Location Bible
Storyboard
Shot Board
Continuity Inspector
Flow Session
Generation Queue
Candidate Comparison
Cost Ledger
Timeline
Final Review
```

### Realtime events

Sử dụng API V2, SSE/WebSocket hiện tại thay vì tạo một backend riêng. WindAgent hiện đã định nghĩa API, worker và client thành các runtime tách biệt trên canonical packages.

### Gate

```text
VP23_PRODUCTION_WORKSPACE_VERIFIED
```

---

# Milestone G — E2E và production hardening

## Phase 24 — PoC E2E có kiểm soát

### Phạm vi

```text
Thời lượng: 30–45 giây
Scene: 2
Shot: 5–7
Nhân vật: 2
Bối cảnh: 1–2
Tỷ lệ: 16:9
Candidate/shot: tối đa 2
Flow session: 1
Concurrency: 1
```

### Test scenario

```text
Ý tưởng
→ VideoClaw-derived screenplay
→ character/location references
→ WindAgent shot plan
→ Flow image generation
→ Flow video generation
→ candidate review
→ audio
→ final MP4
→ production report
```

### Acceptance gate

* Tất cả artifact truy vết được.
* Không submit trùng.
* Resume được sau khi đóng browser.
* Có human takeover.
* Character không bị tráo.
* Ít nhất 80% shot không cần thao tác thủ công ngoài approval.
* Final video vượt `ffprobe`.
* Budget không vượt mức được duyệt.
* Không false PASS.
* Không import từ upstream quarantine.

### Verdict

```text
VP24_E2E_POC_PASSED
```

---

## Phase 25 — Reliability, chaos và failure injection

### Test

* Kill worker khi Flow đang generate.
* Kill browser sau submit.
* Mất mạng.
* Session hết hạn.
* Selector thay đổi.
* Download file 0 byte.
* Output không có video stream.
* Flow báo insufficient credits.
* CAPTCHA xuất hiện.
* User cancel.
* Database restart.
* Duplicate event.
* Lease expiry.
* Stale worker write.
* Flow project bị xóa thủ công.

### Gate

```text
VP25_RECOVERY_AND_CHAOS_VERIFIED
```

---

## Phase 26 — Security và privacy hardening

### Kiểm tra

* Browser profile encryption.
* Secret redaction.
* Domain allowlist.
* Upload allowlist.
* File sandbox.
* Path traversal.
* SSRF.
* Prompt injection từ web asset.
* Malicious image metadata.
* Destructive browser action confirmation.
* Payment gate.
* Audit logging.
* Account screenshot redaction.
* Data retention.
* Project deletion.

### Gate

```text
VP26_SECURITY_VERIFIED
```

---

## Phase 27 — CI matrix và release certification

### CI bắt buộc

```text
Python unit
Architecture imports
Canonical schema
Database migrations
SQLite
PostgreSQL
Worker recovery
Browser adapter mock
Browser contract tests
Frontend unit
Frontend build
Desktop unit
Desktop build
FFmpeg verification
License/notice check
Third-party manifest check
```

### Không chạy Flow live trong mọi PR

Phân chia:

```text
PR CI:
    mocked Flow contract tests

Nightly/manual:
    authenticated Flow smoke test

Release candidate:
    controlled real-credit E2E
```

### Final artifacts

```text
artifacts/video_production/final/
├── implementation_manifest.json
├── upstream_manifest.json
├── test_matrix.json
├── real_flow_e2e_receipt.json
├── cost_report.json
├── security_report.json
├── architecture_report.json
├── known_limitations.md
└── final_verdict.md
```

### Verdict cuối

```text
VIDEO_PRODUCTION_PLATFORM_VERIFIED
READY_FOR_CONTROLLED_RELEASE
```

---

# Thứ tự dependency bắt buộc

```text
Phase 0
  ↓
Phase 1 ── Phase 2
  └────┬─────┘
       ↓
Phase 3
       ↓
Phase 4 → Phase 5 → Phase 6 → Phase 7
                         │
                         ▼
Phase 8 → Phase 9 → Phase 10 → Phase 11
                                  │
                                  ▼
Phase 12 → Phase 13 → Phase 14 → Phase 15 → Phase 16
                                  │
                                  ▼
Phase 17 → Phase 18 → Phase 19 → Phase 20
                                  │
                                  ▼
Phase 21 → Phase 22 → Phase 23
                                  │
                                  ▼
Phase 24 → Phase 25 → Phase 26 → Phase 27
```

Không nên bắt đầu Flow automation trước khi hoàn tất tối thiểu:

```text
Phase 3  Canonical protocol
Phase 8  Director foundation
Phase 9  Shot graph
Phase 11 Prompt compiler
Phase 12 Browser runtime
```

Nếu làm ngược thứ tự, browser automation sẽ bị gắn chặt vào dữ liệu tạm thời và phải viết lại.

---

# Chiến lược branch và commit

Không triển khai toàn bộ trên một branch.

```text
feat/video-production-phase0-baseline
feat/video-production-phase1-upstream
feat/video-production-phase3-protocol
feat/video-production-phase4-videoclaw-intake
feat/video-production-phase6-preproduction
feat/video-production-phase8-director
feat/video-production-phase12-browser-runtime
feat/video-production-phase13-flow
feat/video-production-phase17-workflow
feat/video-production-phase24-e2e
```

Mỗi phase:

1. Branch từ SHA đã được xác minh.
2. Không sửa phase trước bằng commit âm thầm.
3. Có phase report.
4. Có test receipt.
5. Có architecture check.
6. PR ở trạng thái draft cho đến khi gate pass.
7. Không merge khi verdict còn `BLOCKED`.
8. Không tự sửa CI ngoài phạm vi phase.

---

# Các quyết định kiến trúc quan trọng

## 1. Không fork VideoClaw rồi chạy nguyên bản

Đúng hơn là:

```text
vendor snapshot
→ characterize
→ extract capability
→ rewrite theo WindAgent contracts
→ retire runtime dependency
```

## 2. Không thêm ViMax làm submodule

ViMax chỉ xuất hiện trong:

```text
research notes
requirements
ADR
attribution
```

Không xuất hiện trong:

```text
runtime dependencies
imports
Docker image
workspace
generated prompts
```

## 3. WindAgent giữ toàn bộ authority

```text
Project authority       → WindAgent
Revision authority      → WindAgent
Task authority          → WindAgent
Artifact authority      → WindAgent
Cost authority          → WindAgent
Approval authority      → WindAgent
Recovery authority      → WindAgent
```

Flow chỉ trả media artifact.

## 4. Browser provider không phải API giả

Không reverse-engineer private endpoint và không intercept token để gọi API nội bộ của Flow. Provider chỉ dùng GUI hợp lệ, bounded actions và human intervention.

## 5. API provider vẫn phải tồn tại

Dù giai đoạn đầu dùng Flow:

```text
MediaGenerationProviderPort
├── GoogleFlowBrowserGenerationProvider
├── GoogleVeoApiGenerationProvider
├── LocalComfyUIGenerationProvider
└── FutureProvider
```

Điều này ngăn toàn hệ thống ngừng hoạt động khi Flow thay đổi UI.

---

# Phạm vi bản phát hành đầu tiên

Bản đầu không nên nhắm đến phim nhiều phút hoặc đa tập.

## Release 0.1

* Một tài khoản Flow.
* Một browser session.
* Một production project.
* Video 30–45 giây.
* Tối đa hai nhân vật.
* Tối đa bảy shot.
* Một approval workflow.
* Text/image/frames-to-video.
* Download và verify.
* TTS đơn giản.
* FFmpeg assembly.
* Resume cơ bản.
* Mock CI + một live smoke test thủ công.

## Hoãn sang release sau

* Multi-account.
* Cloud browser.
* Headless Flow.
* Multi-user collaboration.
* Render hàng chục shot song song.
* Tự động mua credits.
* Phim dài.
* Lip-sync phức tạp.
* Multi-language dubbing.
* Automatic publishing.
* Social media distribution.
* Video editing timeline nâng cao.

---

# Ưu tiên triển khai thực tế

Thứ tự có giá trị cao nhất là:

```text
1. Phase 0–3: protocol và governance
2. Phase 4–7: VideoClaw pre-production kernel
3. Phase 8–11: Director Layer
4. Phase 12–16: Flow Browser Provider
5. Phase 17–20: orchestration, cost và review
6. Phase 21–24: final video PoC
7. Phase 25–27: hardening và release
```

Tôi chưa thay đổi repository hoặc tạo branch trong lần này; đây là roadmap kiến trúc và triển khai để dùng làm authority trước khi bắt đầu Phase 0.

[1]: https://github.com/HITsz-TMG/VideoClaw/blob/main/README_EN.md "VideoClaw/README_EN.md at main · HITsz-TMG/VideoClaw · GitHub"
[2]: https://github.com/hkuds/vimax "GitHub - HKUDS/ViMax: \"ViMax: Agentic Video Generation (Director, Screenwriter, Producer, and Video Generator All-in-One)\" · GitHub"
[3]: https://github.com/HKUDS/ViMax/raw/refs/heads/main/pipelines/script2video_pipeline.py "raw.githubusercontent.com"
[4]: https://labs.google/fx/tools/flow?utm_source=chatgpt.com "Google Flow - AI Creative Studio for Video, Images & Custom Tools"
[5]: https://github.com/vercel-labs/agent-browser/blob/main/skill-data/core/SKILL.md?utm_source=chatgpt.com "agent-browser/skill-data/core/SKILL.md at main · vercel-labs/agent-browser · GitHub"
[6]: https://github.com/vercel-labs/agent-browser/blob/main/README.md?utm_source=chatgpt.com "agent-browser/README.md at main · vercel-labs/agent-browser · GitHub"
[7]: https://support.google.com/flow/answer/16526234?hl=en&utm_source=chatgpt.com "Manage your Google Flow credits - Computer - Google Flow Help"
