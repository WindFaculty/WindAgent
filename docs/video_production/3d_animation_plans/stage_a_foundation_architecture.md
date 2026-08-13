# Stage A — Kiến trúc lại nền tảng

## 1. Kết quả cần đạt

Stage A tạo ranh giới kiến trúc mới trước khi thêm Blender: đóng băng baseline, thay domain generative-video bằng Production IR trung lập engine, rồi mới loại bỏ Google Flow. Kết thúc Stage, screenplay/Director/continuity còn hoạt động nhưng không package canonical nào phụ thuộc Flow hoặc khái niệm `TEXT_TO_VIDEO`.

## 2. Điều kiện đầu vào

- Authority: `docs/video_production/3d_animation_plans/README.md` + các kế hoạch Stage (bản `road_map.md` cũ đã được thay thế bởi Studio Roadmap 1; 3D animation track không còn phụ thuộc nó).
- Worktree được kiểm kê; thay đổi của người dùng không bị ghi đè.
- Xác định candidate SHA và bộ command baseline thực sự chạy được trên Windows.
- Phân biệt Google Gemini model provider chung với Google Flow browser runtime; Phase 2 chỉ retire Flow.

## 3. Phase 0 — Baseline Freeze & Blender Migration Contract

### Backlog

1. Ghi `baseline_sha`, branch, dirty state, Python/Node/FFmpeg version và platform vào `baseline_commit.json`.
2. Chạy và lưu receipt cho architecture checker, full Python tests, Web/Desktop unit/build và video-production contract tests.
3. Snapshot schema/domain công khai hiện tại, đặc biệt:
   - `GenerationMode`, `GenerationRequest`, `GenerationCandidate`;
   - `MediaGenerationProviderPort`;
   - `FlowGenerationSpecification` và `GenerationModeDecision`;
   - workflow, event, storage key và API payload có liên quan.
4. Lập inventory theo loại `DELETE`, `MIGRATE`, `KEEP_GENERAL`, `HISTORICAL_ONLY` cho code, docs, tests, config và artifacts Flow.
5. Lập dependency map inbound/outbound cho `tools/windagent_tools/google_flow/`; đánh dấu browser code dùng chung và code chỉ phục vụ Flow.
6. Viết migration contract mô tả compatibility window, schema version mới, event migration, rollback và điều kiện xóa adapter tạm.

### Evidence và gate

```text
artifacts/video_production_3d/phase_00/
├── baseline_commit.json
├── toolchain_inventory.json
├── test_baseline.json
├── schema_snapshot.json
├── flow_dependency_inventory.json
└── phase_verdict.json
```

Gate `VP3D_P0_BASELINE_FROZEN` chỉ pass khi baseline có thể tái chạy, mọi dependency Flow đã được phân loại và Phase 0 không chứa thay đổi nghiệp vụ.

## 4. Phase 1 — Canonical Production IR

### Mô hình và contract

Tạo package `core/windagent_core/domain/video_production/production_ir/` với các model immutable, ID ổn định và version rõ ràng:

```text
ProductionIrDocument
ShotExecutionIntent
SceneDescription
CharacterInstance / PropInstance / EnvironmentInstance
CameraTrack / AnimationTrack / FacialTrack / DialogueTrack
LightRig / SimulationTrack / RenderProfile / RenderIntent
```

Tạo `ProductionEnginePort` trong `core/windagent_core/contracts/video_production/`. Port nhận typed plan/artifact reference, không nhận prompt Flow và không lộ `bpy`.

### Backlog migration

1. Lập mapping field-by-field từ `VideoProductionPackage v1`, `Shot`, `GenerationModeDecision`, `FlowGenerationSpecification` và `GenerationRequest` sang IR mới.
2. Thay `GenerationMode` bằng execution intent mô tả actor/action/camera/duration/dialogue/assets; engine adapter tự compile cách thực hiện.
3. Tách phần prompt có giá trị sáng tạo khỏi phần provider-specific. Prompt compiler cũ chỉ tồn tại trong compatibility layer có hạn sử dụng.
4. Định nghĩa canonical serialization JSON/Pydantic, schema versioning, canonical hash và validation rules.
5. Gắn URI/hash cho glTF, FBX, USD và `.blend`; `.blend` luôn là derived artifact.
6. Định nghĩa events tối thiểu: `ProductionIrCreated`, `ProductionIrLocked`, `EngineJobSubmitted`, `EngineJobCompleted`, `EngineJobFailed`, `DerivedArtifactPublished`.
7. Cập nhật storage/invalidation để thay đổi track chỉ invalidate đúng scene/shot/output phụ thuộc.
8. Cung cấp reader/migrator cho artifact cũ trong thời gian chuyển đổi; không dual-write vô thời hạn.

### Kiểm thử

- JSON round-trip và canonical hash ổn định.
- Unknown field/version xử lý fail-closed theo policy.
- Không model domain nào import Flow, Blender hoặc Unreal SDK.
- Cùng một IR có thể được fake engine adapter consume trong contract test.
- Thay dialogue chỉ invalidates audio/facial/final cut; thay camera chỉ invalidates scene compile và render phụ thuộc.
- Legacy fixture chuyển sang IR mới không mất ID, ordering, provenance và approval state.

Gate: `VP3D_P1_ENGINE_NEUTRAL_IR_VERIFIED`.

## 5. Phase 2 — Hard Removal Google Flow

### Thứ tự xóa an toàn

1. Chuyển các guarantee dùng chung sang engine-neutral services: idempotency, cancellation, retry classification, artifact hashing, provenance, fail-closed review và durable recovery.
2. Chuyển composition root/workflow/API/UI sang `ProductionEnginePort` và schema IR mới.
3. Xóa exports/imports/config/secrets cho Flow, rồi xóa `tools/windagent_tools/google_flow/`.
4. Xóa hoặc viết lại Flow-specific tests, scripts verification và UI panels. Historical evidence được archive, không được coi là current release evidence.
5. Cập nhật docs, examples, env template, build/package manifest và architecture rules.
6. Thêm regression scan chặn tái xuất hiện runtime symbols/path Flow. Scan phải loại trừ rõ historical archive và chính rule kiểm tra.

### Negative tests bắt buộc

- Import một module Flow từ canonical package phải làm architecture test fail.
- Config chứa Flow credential/runtime key phải bị validator báo residue.
- Worker restart/cancel/retry vẫn hoạt động qua fake `ProductionEnginePort` sau khi Flow bị xóa.
- Google Gemini LLM provider không bị xóa nhầm.

Gate `VP3D_P2_GOOGLE_FLOW_REMOVED` cần runtime imports, schemas, config, tests và UI dependencies bằng 0; historical artifacts phải được đánh dấu archive.

## 6. Trình tự commit đề xuất

```text
docs(3d): freeze baseline and migration contract
feat(3d-ir): add engine-neutral production IR and port
feat(3d-ir): migrate workflow, storage and events
test(3d-ir): add compatibility and architecture matrices
refactor(flow): move reusable guarantees behind neutral services
chore(flow): remove Flow runtime, config, UI and current tests
docs(3d): publish Stage A evidence and verdict
```

## 7. Rủi ro chặn Stage

- Xóa Flow trước khi consumer chuyển sang IR làm runtime gãy hàng loạt.
- Chuỗi `flow` trong historical docs gây false positive; cần archive allowlist hẹp.
- `GenerationRequest` đang được storage/workflow tham chiếu; migration phải kiểm tra persisted data thật.
- Browser là capability dùng chung của agent; chỉ xóa phần browser dành riêng cho Flow.

Stage hoàn thành khi cả ba gate pass trên cùng candidate SHA và full regression không thấp hơn baseline ngoài các test Flow đã được retirement manifest chấp nhận.
