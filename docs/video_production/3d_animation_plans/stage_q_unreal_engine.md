# Stage Q — Unreal Engine

## 1. Kết quả cần đạt

Thêm `UnrealEngineAdapter` sau khi Blender pipeline đã ổn định, so sánh parity bằng cùng Production IR, rồi chuyển final scene/render sang Unreal theo rollout có kiểm soát. Blender vẫn là công cụ asset authoring/cleanup/UV/rig/animation preparation.

## 2. Điều kiện đầu vào

- Stages P36–P37 verified với golden scene/asset interchange fixtures.
- Pin một Unreal Engine version cụ thể tại thời điểm bắt đầu Stage; không dùng `latest` trong manifest.
- Xác định hardware/support matrix, licensing, command-line automation và CI/manual test strategy.
- Có rollback giữ Blender renderer hoạt động cho cùng IR revision.

## 3. Phase 38 — Unreal Adapter PoC

### Package mục tiêu

```text
tools/windagent_tools/production_engines/unreal/
├── runtime/
├── importer/
├── compiler/
├── camera/
├── animation/
├── lighting/
└── rendering/
```

### Backlog

1. Implement capability probe, launcher/supervisor/receipt theo semantics `ProductionEnginePort`.
2. Import một golden `EngineScenePackage`; map instances, camera, animation, facial, lighting intent và render profile.
3. Tạo project/map derived, không coi Unreal project là source of truth.
4. Render một scene/shot và xuất media/metadata theo artifact contract hiện có.
5. So sánh Blender/Unreal về semantic fidelity, visual quality, render time, VRAM, failure recovery và unsupported features.
6. PoC không thay default engine và không xóa Blender fallback.

Gate nội bộ: `VP3D_P38_UNREAL_ADAPTER_POC_VERIFIED`.

## 4. Phase 39 — Blender → Unreal Asset Pipeline

### Backlog

1. Chốt ownership: Blender cho model cleanup, UV, rig và animation preparation; Unreal cho scene, camera, lighting và final render.
2. Tạo publish profile cho skeletal/static mesh, textures/materials, LOD, morph targets và animations.
3. Map canonical asset/master IDs thành Unreal asset registry path mà không dùng display name làm identity.
4. Validate import settings, units/axis, skeleton compatibility, material fidelity, collision, LOD và animation timing.
5. Detect source revision change và reimport đúng dependencies; manual Unreal edits cần override manifest hoặc bị coi là drift.
6. Batch/recovery/idempotency cho import/reimport; failed import không corrupt approved library.

Gate nội bộ: `VP3D_P39_BLENDER_UNREAL_ASSET_PIPELINE_VERIFIED`.

## 5. Phase 40 — Unreal Production Renderer

### Parity và rollout

1. Đạt contract parity cho compile, render, cancel, retry, resume, artifact receipt, review và post-production.
2. Chạy golden scene rồi multi-scene episode bằng cùng IR/assets; so quality/performance/reliability.
3. Thêm engine selection policy theo project/revision; không auto-switch giữa run.
4. Rollout: opt-in/internal → shadow comparison → controlled default; Blender fallback giữ đến khi exit metrics ổn định.
5. Default chỉ chuyển khi Unreal không làm mất blocking semantics và có recovery/evidence tương đương.
6. Sau cutover mới cân nhắc deprecate Blender scene rendering; asset authoring vẫn được support.

Gate nội bộ: `VP3D_P40_UNREAL_PRODUCTION_RENDERER_VERIFIED`.

## 6. Test matrix

- Capability/version mismatch, missing plugin/project, command timeout và engine crash.
- Static/skinned/facial/animation/camera/light golden fixtures.
- Blender → Unreal reimport sau asset revision; unrelated asset không bị rebuild.
- Cancel/resume/duplicate dispatch và stale worker completion.
- Engine selection pin theo revision; restart không đổi engine.
- Unsupported feature tạo degradation report + approval, không drop silent.
- Rollback sang Blender dùng cùng IR không cần migrate screenplay/Director/audio.

## 7. Evidence và quyết định cutover

```text
artifacts/video_production_3d/phase_38..40/
├── unreal_toolchain_manifest.json
├── capability_probe.json
├── import_mapping_manifest.json
├── blender_unreal_parity_report.json
├── quality_performance_comparison.json
├── recovery_test_receipt.json
├── rollout_readiness.json
└── phase_verdict.json
```

Cutover decision phải nêu rõ feature parity, visual acceptance, throughput, peak resources, crash/recovery rate, known degradations và rollback rehearsal.

## 8. Rủi ro

- Unreal automation/plugin API thay đổi theo version; pin engine + plugin hashes và contract tests.
- Visual parity không đồng nghĩa bit parity; đánh giá semantic intent và approved quality rubric.
- Chuyển renderer quá sớm có thể tạo hai production paths; chỉ một engine là default cho mỗi locked revision.
