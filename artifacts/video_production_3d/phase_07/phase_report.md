# Phase 07 — Asset Normalization (Stage C)

## Kết quả

`AssetNormalizerPort` là cổng duy nhất mọi asset đi qua trước khi Scene Compiler tiêu thụ.
Pipeline canonical `ingest -> security -> parse -> unit/axis -> mesh -> material/texture ->
poly/VRAM budget -> LOD -> preview -> publish` chạy end-to-end trên máy thật với
Blender 4.5.12 LTS (REAL job: sandboxed import validate, LOD Decimate, Cycles turntable
preview) và trong CI với fake deterministic.

## Backlog Phase 7 — trạng thái

1. **Canonical metadata meter + Z-up; adapter chuyển trục thực tế** — DONE:
   `CanonicalMetadata` (unit=METERS, up_axis=Z_UP, scale_factor derive từ detected, fail-closed).
2. **Validate non-manifold, normals, UV, material slots, missing textures, unsupported shaders, skeleton, animation** — DONE:
   `MeshValidator` host-side + `_mesh_stats` (bmesh) trong Blender job; blocking issues ⇒ BLOCKED.
3. **PBR material; texture content-addressed, giới hạn resolution/bit depth, color-space metadata** — DONE:
   `TextureNormalizer` (LANCZOS downscale, strip metadata, SHA-256, color-space metadata).
4. **LOD theo policy, không overwrite source; mỗi LOD có hash + quality metrics** — DONE:
   `LodPolicyApplier` (NONE/SINGLE/MULTI), decimation là Blender job, LOD0 = source reference.
5. **VRAM estimate trước preview; vượt hard limit ⇒ BLOCKED** — DONE:
   `VramEstimator`; BLOCKED ⇒ không render mù (test chứng minh preview không bao giờ chạy).
6. **Turntable/thumbnail bằng deterministic Blender profile Stage B** — DONE:
   `execute_asset_job.py` (pure stdlib, auto-execution tắt), Cycles CPU samples=8, 512x288, Standard.
7. **Publish asset bundle immutable** — DONE:
   `AssetBundlePublisher`: manifest + validation_report + provenance + textures + lods + preview,
   bundle hash deterministic theo sorted (path, sha256).

## Kiến trúc

```text
core/domain/.../asset_normalization/        DTO + enums + errors (engine-neutral)
core/contracts/.../asset_normalizer.py      AssetNormalizerPort
tools/media_assets/normalization/           host pipeline + parsers + checks + vram + textures
                                            + lod + preview + bundle + job_runner + fakes
tools/production_engines/blender/           BlenderAssetJobRunner + execute_asset_job.py
apps/worker/.../composition.py              _register_asset_normalizer (guard WINDAGENT_ASSET_NORMALIZER=1)
```

## Kiểm thử

- Phase 7 suite: 62 passed / 0 failed (domain 17, host pipeline 18, job contract 8, integration 10, architecture 9).
- Regression VP3D Phase 5/6: 198 passed / 0 failed.
- Negative: archive/executable/shebang reject trước parse; content-hash mismatch; traversal texture URI;
  VRAM/poly BLOCKED không preview; no-job-runner fail closed.
- Ruff: 0 violation; architecture checker: verdict PASS, 0 violation.
- Full workspace regression: 2164 passed / 4 failed / 36 skipped — 4 failures đều PRE-EXISTING,
  không liên quan Phase 7 (doc-purge chore 5662ede làm mất ADR 0006 + director_research docs khiến
  test_phase00_docs_exist / test_phase03_verifier_no_write fail; test_phase27_release là baseline defect VP3D_BASELINE_001).
- Real machine: `verify_phase7_normalization.py` — status READY, 6 tris, LOD1 blender_job, 12 preview frames, bundle hash `c9c3eba3e556b6f7`.

## Evidence

`artifacts/video_production_3d/phase_07/`: input_manifest.json, implementation_manifest.json,
test_receipt.json, architecture_report.json, risk_register.json, phase_report.md,
phase_verdict.json, real_machine_evidence.json.

## Gate

`VP3D_P7_ASSET_NORMALIZATION_VERIFIED` — một asset local, một Internet fixture và một
generated/fake provider asset đi qua full pipeline; malicious fixtures fail-closed.

## Known limitations / deferred

- Quad-dominance analysis cần engine-side (host chỉ cảnh báo).
- `asset.<ext>` trong bundle là copy source; normalize geometry thực sự là `normalized.blend`
  trong Blender job path.
- GPU render chưa available (CPU-only baseline, xem Phase 3 unlock conditions).

Thời điểm: 2026-08-08T02:34:44.479918+00:00
