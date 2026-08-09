# Kế hoạch Stage D — Universal Production Asset Domain

## 1. Thông tin kế hoạch

| Thuộc tính | Giá trị |
| --- | --- |
| Stage | D |
| Phạm vi | UI19–UI33 |
| Kết quả chính | Universal Asset Manager production-ready |
| Dependency đầu vào | Stage A và Stage B/UI5–UI7 pass |
| Có thể chạy song song | Stage C |
| Bàn giao cho | Stage E, F, H và I |
| Độ phức tạp tương đối | XXL |

## 2. Mục tiêu

Mở rộng asset pipeline hiện có thành Universal Production Resource Library. Sau Stage D:

- asset có taxonomy theo meaning, không bị đồng nhất với format/MIME;
- asset và asset revision có aggregate/persistence rõ ràng;
- bytes không bị overwrite;
- lifecycle và processing status độc lập;
- query/command API hỗ trợ thư viện lớn;
- inspector thể hiện validation, provenance, license, dependency và usage;
- 3D và non-3D resource có preview phù hợp;
- acquisition/generation đi qua resolver/job pipeline;
- asset version replacement luôn có impact review;
- unknown/incompatible license bị chặn server-side.

## 3. Baseline và capability tái sử dụng

Tái sử dụng:

- `ReferenceAsset` và content-addressed media concepts;
- asset resolution contracts/ports;
- `AssetLifecycleState` và `AssetStateMachine`;
- provenance/license constraints hiện có;
- asset normalization models, reports, preview results và errors;
- character, rigging, animation, facial, audio, lighting và camera capabilities;
- durable command/event/job foundation của Stage B;
- shared shell, state, platform adapter của Stage A.

Cần mở rộng:

- universal taxonomy;
- `ProductionAsset`/`AssetRevision` aggregate;
- repository/query/command API;
- shared Asset Workspace;
- preview registry/viewers;
- acquisition/generation UX;
- usage/dependency/version impact read models.

## 4. Phạm vi

### Trong phạm vi

- UI19–UI33 đầy đủ;
- asset domain/persistence/API;
- upload/import/acquisition/generation request;
- preview derivatives và viewers;
- job monitor;
- license governance;
- usage/dependency;
- version replacement.

### Ngoài phạm vi

- screenplay entity resolver UI của Stage E;
- universal agent proposal của Stage F;
- final render implementation;
- full Video Workspace.

## 5. Kiến trúc mục tiêu

```text
ProductionAsset
    |
    +-- active_revision_id ----> AssetRevision (immutable)
    |                                 |
    |                                 +-- content hash / artifact
    |                                 +-- normalization report
    |                                 +-- validation report
    |                                 +-- preview derivatives
    |                                 +-- provenance/license evidence
    |
    +-- lifecycle state
    +-- tags/metadata
    +-- bindings
    +-- dependencies

Asset command → durable job → processing events → read model → shared UI
```

## 6. Kế hoạch UI19 — Production Asset Taxonomy

### Taxonomy mục tiêu

```text
CHARACTER, ENVIRONMENT, PROP
MODEL_3D, MATERIAL, TEXTURE
RIG, ANIMATION, FACIAL_PROFILE
VOICE_PROFILE, VOICE_SAMPLE, DIALOGUE_AUDIO
MUSIC, SFX, AMBIENCE
LIGHT_RIG, CAMERA_RIG
REFERENCE_IMAGE, STORYBOARD
DOCUMENT, OTHER
```

Ba trục tách biệt:

```text
ProductionAssetKind = ý nghĩa production
MediaType           = dạng biểu diễn vật lý
MimeType            = encoding/file format
```

### Backlog

- `D-UI19-01`: inventory enum/type hiện có;
- `D-UI19-02`: thêm `ProductionAssetKind`;
- `D-UI19-03`: chốt kind/media/mime compatibility matrix;
- `D-UI19-04`: mapping `ReferenceAsset` legacy sang taxonomy mới;
- `D-UI19-05`: unknown/future kind handling;
- `D-UI19-06`: migration/backfill;
- `D-UI19-07`: update OpenAPI/TS enums;
- `D-UI19-08`: architecture docs/examples;
- `D-UI19-09`: compatibility tests;
- `D-UI19-10`: kiểm tra không phá asset resolution/normalization hiện có.

### Acceptance

- kind không suy luận mù từ extension;
- một character có thể dùng model, material, rig, voice dependencies;
- legacy asset đọc được trong compatibility window;
- enum mới không làm client crash.

## 7. Kế hoạch UI20 — Asset Aggregate

### Models

```text
ProductionAsset
├── assetId, kind, name, description
├── lifecycle, activeRevisionId
├── tags, source, license
├── projectBindings, dependencies
└── metadata

AssetRevision
├── revisionId, assetId, supersedes
├── contentHash, format, normalizedFormat
├── previewArtifacts, validationReport
├── provenance, createdAt
└── artifact locator/ID
```

### Backlog

- `D-UI20-01`: define aggregate root/invariants;
- `D-UI20-02`: define immutable revision entity;
- `D-UI20-03`: map normalization outputs vào revision;
- `D-UI20-04`: content hash canonicalization;
- `D-UI20-05`: artifact repository reference, không internal path trong DTO;
- `D-UI20-06`: database schema/migrations;
- `D-UI20-07`: asset/revision repositories;
- `D-UI20-08`: active revision pointer update rules;
- `D-UI20-09`: supersedes lineage;
- `D-UI20-10`: dedupe bytes nhưng giữ provenance/metadata identity;
- `D-UI20-11`: concurrent create/update tests;
- `D-UI20-12`: immutable bytes/hash tests;
- `D-UI20-13`: legacy migration tests.

### Acceptance

- bytes/revision cũ không overwrite;
- active revision là explicit pointer;
- lineage query được;
- identical content không làm mất provenance khác;
- restart database giữ aggregate state.

## 8. Kế hoạch UI21 — Asset Lifecycle

### Hai state machines

Lifecycle/business:

```text
DISCOVERED → DOWNLOADED → VALIDATED
                         ├→ LICENSE_UNKNOWN
                         ├→ APPROVED → BOUND_TO_PROJECT
                         └→ REJECTED
```

Processing/operational:

```text
IDLE, DOWNLOADING, NORMALIZING, GENERATING_PREVIEW,
VALIDATING, RIGGING, PROCESSING, FAILED
```

### Backlog

- `D-UI21-01`: reconcile state machine hiện có với roadmap;
- `D-UI21-02`: define lifecycle transition matrix;
- `D-UI21-03`: define processing state machine;
- `D-UI21-04`: actor/reason/permission per transition;
- `D-UI21-05`: invalid transition fail closed;
- `D-UI21-06`: job event → processing projection;
- `D-UI21-07`: lifecycle event → library projection;
- `D-UI21-08`: failure/retry không tự đổi approval;
- `D-UI21-09`: terminal/cancel semantics;
- `D-UI21-10`: exhaustive transition tests;
- `D-UI21-11`: concurrency/idempotency tests.

### Acceptance

- processing failure không biến thành business rejection ngoài policy;
- approve không xảy ra chỉ vì job hoàn tất;
- retry không reset provenance/license;
- invalid transition không mutate.

## 9. Kế hoạch UI22 — Asset Query API

### Endpoints

```http
GET /api/v2/video-production/assets
GET /api/v2/video-production/assets/{asset_id}
GET /api/v2/video-production/assets/{asset_id}/revisions
GET /api/v2/video-production/assets/{asset_id}/validation
GET /api/v2/video-production/assets/{asset_id}/provenance
GET /api/v2/video-production/assets/{asset_id}/bindings
GET /api/v2/video-production/assets/{asset_id}/dependencies
```

### Backlog

- `D-UI22-01`: list/detail query services;
- `D-UI22-02`: revision/validation/provenance/binding/dependency queries;
- `D-UI22-03`: cursor pagination;
- `D-UI22-04`: deterministic sort;
- `D-UI22-05`: project/kind/lifecycle/processing/license/source/format/tag/query filters;
- `D-UI22-06`: search index strategy;
- `D-UI22-07`: thumbnail/summary projection tránh N+1;
- `D-UI22-08`: signed artifact access/token;
- `D-UI22-09`: project authorization;
- `D-UI22-10`: OpenAPI/TS generation;
- `D-UI22-11`: MSW/fake fixtures;
- `D-UI22-12`: large-library load tests;
- `D-UI22-13`: no-internal-path contract tests.

### Acceptance

- không load toàn bộ library vào browser;
- filter/sort/pagination stable;
- asset/project không có quyền không bị lộ qua counts/search;
- response không chứa path nội bộ;
- large fixture nằm trong performance budget.

## 10. Kế hoạch UI23 — Asset Command API

### Command catalog

```text
IMPORT_ASSET, UPLOAD_ASSET
DISCOVER_ASSET, DOWNLOAD_ASSET
REQUEST_ASSET_GENERATION
NORMALIZE_ASSET, VALIDATE_ASSET
APPROVE_ASSET, REJECT_ASSET, UPDATE_LICENSE
CREATE_ASSET_REVISION
BIND_ASSET, UNBIND_ASSET
ARCHIVE_ASSET
```

### Backlog

- `D-UI23-01`: payload schema cho từng command;
- `D-UI23-02`: register vào Stage B dispatcher;
- `D-UI23-03`: staged upload contract;
- `D-UI23-04`: file size/type/hash/security validation;
- `D-UI23-05`: URL acquisition validation;
- `D-UI23-06`: job dispatch cho download/generate/normalize/validate/preview;
- `D-UI23-07`: approve/reject/license permission;
- `D-UI23-08`: revision-aware binding;
- `D-UI23-09`: archive giữ historical references;
- `D-UI23-10`: event/audit cho mọi command;
- `D-UI23-11`: restart/idempotency tests;
- `D-UI23-12`: partial job-dispatch failure compensation;
- `D-UI23-13`: frontend typed actions/hooks.

### Acceptance

- mỗi command idempotent/revision-aware/auditable/event-emitting;
- job-creating command không tạo duplicate job khi retry;
- invalid upload/URL không đi vào canonical library;
- archive không phá historical production revision.

## 11. Kế hoạch UI24 — Asset Library Page

### Backlog

- `D-UI24-01`: `AssetWorkspace` shared layout;
- `D-UI24-02`: search bar và filter panel;
- `D-UI24-03`: grid view;
- `D-UI24-04`: list view;
- `D-UI24-05`: selected asset/inspector integration;
- `D-UI24-06`: route giữ filter/view/selection;
- `D-UI24-07`: server pagination/infinite paging;
- `D-UI24-08`: thumbnail lazy loading;
- `D-UI24-09`: virtualization;
- `D-UI24-10`: loading/empty/error/quarantine states;
- `D-UI24-11`: safe bulk operations;
- `D-UI24-12`: keyboard/accessibility;
- `D-UI24-13`: Desktop/Web component tests;
- `D-UI24-14`: object URL/resource cleanup.

### Acceptance

- query state và URL đồng bộ;
- grid/list dùng cùng source of truth;
- filter không fetch race/hiển thị result project cũ;
- large library scroll/search usable;
- thumbnail failure không crash card/list.

## 12. Kế hoạch UI25 — Asset Inspector

### Tabs

```text
Overview, Preview, Versions, Validation,
Provenance, License, Dependencies, Usage
```

### Backlog

- `D-UI25-01`: tab shell và lazy query;
- `D-UI25-02`: Overview fields;
- `D-UI25-03`: Versions lineage/active revision;
- `D-UI25-04`: Validation summary + details;
- `D-UI25-05`: Provenance source/provider/author/URL/model/prompt hash/seed/time;
- `D-UI25-06`: License evidence/constraints;
- `D-UI25-07`: Dependencies/Usage hosts;
- `D-UI25-08`: cancel query khi selection đổi;
- `D-UI25-09`: copy/download actions theo permission;
- `D-UI25-10`: sanitize secrets/raw logs/prompts;
- `D-UI25-11`: empty/not-applicable states;
- `D-UI25-12`: accessibility tests.

### Acceptance

- mỗi tab gắn đúng asset revision;
- selection nhanh không hiển thị stale tab data;
- provenance/license/validation có source/time/version;
- không lộ secret hoặc internal locator.

## 13. Kế hoạch UI26 — Asset License Governance

### Backlog

- `D-UI26-01`: chuẩn hóa license state/evidence/constraint;
- `D-UI26-02`: define eligibility policy;
- `D-UI26-03`: `LICENSE_UNKNOWN` chặn final-production use;
- `D-UI26-04`: attach/update license command;
- `D-UI26-05`: evidence artifact hash/source;
- `D-UI26-06`: reject workflow;
- `D-UI26-07`: UI warning không có “Use Anyway” mặc định;
- `D-UI26-08`: render/finalization server gate;
- `D-UI26-09`: expiry/revocation/incompatibility checks;
- `D-UI26-10`: new revision inheritance policy;
- `D-UI26-11`: audit history;
- `D-UI26-12`: negative tests bypassing UI.

### Acceptance

- UI không phải enforcement duy nhất;
- unknown/expired/revoked/incompatible license fail closed;
- license update có actor/reason/evidence;
- asset revision mới không tự kế thừa sai.

## 14. Kế hoạch UI27 — 3D Preview System

### Pipeline

```text
FBX/USD/.blend/glTF
→ backend Preview Compiler
→ versioned GLB derivative + thumbnail/stats
→ authorized artifact endpoint
→ shared web renderer
```

### Backlog

- `D-UI27-01`: preview derivative contract/version;
- `D-UI27-02`: compiler/worker integration;
- `D-UI27-03`: cache theo content hash/profile version;
- `D-UI27-04`: signed artifact access;
- `D-UI27-05`: Three.js/React Three Fiber viewer;
- `D-UI27-06`: orbit/zoom/pan;
- `D-UI27-07`: wireframe/skeleton/bounding box;
- `D-UI27-08`: material/texture toggles;
- `D-UI27-09`: animation playback;
- `D-UI27-10`: mesh/material/texture/VRAM stats;
- `D-UI27-11`: geometry/texture/memory limits;
- `D-UI27-12`: WebGL unavailable fallback;
- `D-UI27-13`: context loss/error recovery;
- `D-UI27-14`: Desktop/Web visual smoke;
- `D-UI27-15`: assert frontend không parse `.blend`.

### Acceptance

- same GLB derivative render trong cả hai app;
- `.blend` không được parse trực tiếp ở client;
- asset lớn/invalid không làm treo app;
- viewer cleanup GPU resources khi unmount.

## 15. Kế hoạch UI28 — Non-3D Resource Preview

### Backlog

- `D-UI28-01`: previewer registry theo kind/media/mime;
- `D-UI28-02`: image viewer;
- `D-UI28-03`: audio waveform/playback/metadata;
- `D-UI28-04`: animation clip selector trên 3D viewer;
- `D-UI28-05`: material sphere derivative;
- `D-UI28-06`: camera rig metadata/optional preview;
- `D-UI28-07`: lighting rig thumbnail;
- `D-UI28-08`: loading/error/unsupported states;
- `D-UI28-09`: media URL lifecycle cleanup;
- `D-UI28-10`: accessibility controls cho playback;
- `D-UI28-11`: format matrix tests.

### Acceptance

- unsupported preview không chặn inspector;
- media controls usable/accessibility pass;
- derivative gắn đúng asset revision;
- signed URL hết hạn có refresh/retry path.

## 16. Kế hoạch UI29 — Asset Acquisition Workspace

### Sources

```text
Upload Local, Import URL, Search Internet,
Generate with Agent, Reuse Existing
```

### Backlog

- `D-UI29-01`: acquisition wizard/state machine;
- `D-UI29-02`: `AssetRequirement` input contract;
- `D-UI29-03`: local upload qua platform adapter;
- `D-UI29-04`: URL import qua backend;
- `D-UI29-05`: library reuse search;
- `D-UI29-06`: resolver provider-agnostic request;
- `D-UI29-07`: candidate source/provenance/license preview;
- `D-UI29-08`: SSRF/scheme/size/content security boundary;
- `D-UI29-09`: resumable/recoverable upload decision;
- `D-UI29-10`: cancel/retry behavior;
- `D-UI29-11`: explicit provider override policy;
- `D-UI29-12`: acquisition E2E fixtures.

### Acceptance

- frontend không hardcode arbitrary resolver implementation;
- untrusted URL/file được validate server-side;
- acquisition tạo candidate/provenance trước approval;
- cancel/retry không tạo duplicate asset.

## 17. Kế hoạch UI30 — Asset Generation Request

### Backlog

- `D-UI30-01`: typed form theo asset kind;
- `D-UI30-02`: description/style/target fields;
- `D-UI30-03`: rig/poly/texture/resource budgets;
- `D-UI30-04`: capability/provider resolution;
- `D-UI30-05`: optional cost/time estimate;
- `D-UI30-06`: idempotent generation command;
- `D-UI30-07`: persist request/provenance trước dispatch;
- `D-UI30-08`: candidate/result model;
- `D-UI30-09`: candidate không auto-approve;
- `D-UI30-10`: cancel/provider failure/partial results;
- `D-UI30-11`: retry policy;
- `D-UI30-12`: deterministic fake provider cho CI.

### Acceptance

- generation request durable và auditable;
- duplicate submit không tạo duplicate job;
- output đi qua normalize/validate/license;
- provider failure có actionable state.

## 18. Kế hoạch UI31 — Asset Job Monitor

### Backlog

- `D-UI31-01`: job read model/projection;
- `D-UI31-02`: card progress summary;
- `D-UI31-03`: job detail current stage/progress/time;
- `D-UI31-04`: sanitized logs/failure;
- `D-UI31-05`: retryable classification/policy;
- `D-UI31-06`: Cancel command;
- `D-UI31-07`: Retry command;
- `D-UI31-08`: reconnect/replay;
- `D-UI31-09`: app/backend restart recovery;
- `D-UI31-10`: orphan/unknown job handling;
- `D-UI31-11`: no-blind-retry tests;
- `D-UI31-12`: telemetry duration/failure/retry.

### Acceptance

- progress không regress ngoài explicit retry;
- reconnect/restart khôi phục state;
- Cancel/Retry có permission/idempotency;
- non-retryable failure không có blind retry.

## 19. Kế hoạch UI32 — Asset Usage & Dependency Graph

### Backlog

- `D-UI32-01`: usage projection project→scene→shot;
- `D-UI32-02`: dependency edge types và asset revisions;
- `D-UI32-03`: query API;
- `D-UI32-04`: cycle/missing dependency validation;
- `D-UI32-05`: usage tree UI;
- `D-UI32-06`: dependency tree/graph UI;
- `D-UI32-07`: lazy expansion cho graph lớn;
- `D-UI32-08`: deep-link node;
- `D-UI32-09`: permission filtering;
- `D-UI32-10`: archived/revision history handling;
- `D-UI32-11`: cycle/large graph tests.

### Acceptance

- dependency gắn explicit revision khi cần;
- cycle/missing edge được báo;
- không leak project qua usage counts;
- node link tới đúng project/revision/entity.

## 20. Kế hoạch UI33 — Asset Version Replacement

### Backlog

- `D-UI33-01`: compare old/candidate asset revision;
- `D-UI33-02`: impact projects/scenes/shots/animations/rerenders;
- `D-UI33-03`: bind impact result với sequence/revision;
- `D-UI33-04`: action current project only;
- `D-UI33-05`: action selected bindings;
- `D-UI33-06`: action create project revision;
- `D-UI33-07`: no global replace default;
- `D-UI33-08`: command batch/transaction strategy;
- `D-UI33-09`: stale impact recompute;
- `D-UI33-10`: rollback/partial failure handling;
- `D-UI33-11`: audit before/after bindings;
- `D-UI33-12`: concurrency tests.

### Acceptance

- replacement không tự lan mọi project;
- user thấy impact trước apply;
- stale result không apply;
- partial failure không tạo mixed/unknown binding state;
- old revision/history còn truy cập được.

## 21. Test strategy

| Tầng | Nội dung |
| --- | --- |
| Domain | taxonomy, aggregate, lifecycle, license, lineage |
| Repository | persistence, pagination, concurrency |
| API | queries, filters, commands, auth, signed artifacts |
| Worker/job | normalize, preview, generation, retry/restart |
| Component | library, inspector, viewers, acquisition, monitor |
| Consumer | Desktop/Web preview and behavior matrix |
| E2E | import/generate → normalize → validate → approve → version |
| Security | upload, URL/SSRF, artifact authorization, secret leakage |

## 22. Rủi ro và giảm thiểu

| Rủi ro | Giảm thiểu |
| --- | --- |
| Taxonomy phá model hiện có | compatibility mapping/migration tests |
| Lifecycle trộn processing | hai state machine riêng |
| Overwrite asset bytes | immutable revisions/content hash |
| Library lớn làm treo UI | server pagination, virtualization |
| Preview file gây crash | backend derivative + resource limits |
| URL import gây SSRF | backend allowlist/validation/network policy |
| License chỉ chặn ở UI | server final-production gate |
| Retry tạo duplicate job | command idempotency |
| Global version replace ngoài ý muốn | explicit scope + impact + stale check |

## 23. Stage gate và exit checklist

Gate đề xuất:

```text
VP3D_UI_ASSET_MANAGER_VERIFIED
```

- [ ] UI19 taxonomy và legacy mapping pass.
- [ ] UI20 immutable asset revisions pass.
- [ ] UI21 lifecycle/processing tests pass.
- [ ] UI22 query/pagination/performance pass.
- [ ] UI23 commands/idempotency/restart pass.
- [ ] UI24 library chạy trong Desktop/Web.
- [ ] UI25 inspector đầy đủ.
- [ ] UI26 server license fail-closed pass.
- [ ] UI27 3D preview matrix pass.
- [ ] UI28 non-3D preview matrix pass.
- [ ] UI29 acquisition security tests pass.
- [ ] UI30 generation flow pass.
- [ ] UI31 job recovery pass.
- [ ] UI32 usage/dependency pass.
- [ ] UI33 version impact/replacement pass.
- [ ] Gate `VP3D_UI_ASSET_MANAGER_VERIFIED` pass.

## 24. Bàn giao

Stage E nhận asset eligibility, requirements search, binding commands, usage/dependency và deep-link IDs.

Stage F nhận asset diff/impact/approval/license operations để đưa vào unified proposal.

Stage I nhận deterministic asset/job fixtures và golden workflow commands.
