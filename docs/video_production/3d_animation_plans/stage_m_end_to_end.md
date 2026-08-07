# Stage M — End-to-End

## 1. Kết quả cần đạt

Chứng minh pipeline tự động từ screenplay đến MP4 ở quy mô tăng dần: 30–60 giây, 2–3 phút, 5 phút, 10 phút và 20 phút. Mỗi nấc chỉ tăng sau khi nấc trước có evidence; Phase 28 tối ưu dựa trên profiling giữa các acceptance run.

## 2. Điều kiện đầu vào

- Stages A–L đã verified trên cùng architecture generation.
- Có một production fixture versioned gồm screenplay, character masters, environment, animation/audio intents và approval state.
- Hardware baseline được ghi: Windows, Blender 4.5 LTS, Cycles, RTX 5060 Laptop 8 GB, RAM 32 GB, i7-14650HX.
- Mọi run có budget về thời gian, disk, retries và manual intervention.

## 3. Phase 25 — 30–60 Second Golden Scene

### Fixture và luồng

Fixture tối thiểu: hai character, một environment, dialogue, walk, interaction, moving camera, lighting, lip-sync, Cycles, audio và FFmpeg.

```text
Script → IR → Assets → Scene → Animation + Audio
→ Facial → Render → Review/Repair → FFmpeg → Final MP4
```

### Acceptance

- Không mở Blender để sửa thủ công.
- Mọi input/output có ID, revision, provenance và content hash.
- Cancel/restart ở ít nhất một node được resume không duplicate.
- Character/voice identity và continuity pass.
- Render frames, audio và final MP4 vượt technical verification.
- Blocking defect fixture bị reject; không false PASS.
- Production report nêu rõ số lần repair và mọi human approval.

Gate: `VP3D_P25_GOLDEN_SCENE_E2E_PASSED`.

## 4. Phase 26 — 2–3 Minute Episode

Phạm vi: ít nhất ba scene, năm shot, hai đến bốn character và nhiều environment.

Backlog acceptance:

1. Reuse character/environment/animation assets thay vì generate lại.
2. Continuity qua scene/shot và stable episode ordering.
3. Audio/asset branches chạy song song; đo critical path và idle time.
4. Kill worker/Blender giữa render, resume frame chunk và partial rerender.
5. Thay một shot/camera/audio cue chỉ invalidates đúng downstream artifacts.
6. Cache report phân biệt hit, miss, invalidated và rejected reuse.

Gate nội bộ: `VP3D_P26_MULTI_SCENE_EPISODE_VERIFIED`.

## 5. Phase 27 — 5-Minute Production Acceptance

Khóa 1080p/24fps/Cycles/single-machine và đo:

```text
preproduction, asset, scene compile, animation, audio,
render, review/repair, post-production, total wall clock,
GPU utilization, peak VRAM, disk IO, cache hit rate
```

Không chỉ báo tổng thời gian; phải có distribution theo scene/shot/frame và critical path. Gate nội bộ: `VP3D_P27_5MIN_PRODUCTION_VERIFIED`.

## 6. Phase 28 — Performance Optimization

### Quy trình

1. Thu `performance_profile.json`, GPU/VRAM profile, scene complexity, asset cache và render time by shot.
2. Xếp hạng bottleneck theo wall-clock contribution; lập hypothesis và benchmark A/B trên fixture cố định.
3. Chỉ áp optimization khi quality gate không regression và kết quả vượt noise threshold.
4. Ưu tiên cache/reuse, instancing, texture/geometry/LOD, adaptive sampling, denoise, bounces, light complexity và scheduling.
5. Mỗi optimization có before/after, profile hash, quality delta và rollback switch.

Không thay Cycles bằng Eevee trong Phase này. Gate nội bộ: `VP3D_P28_PROFILED_OPTIMIZATION_VERIFIED`.

## 7. Phase 29 — 10-Minute Episode Acceptance

Run production với asset-ready assumption được khai báo rõ. Target preferred `≤ 3h`; nếu vượt, verdict phải là `PERFORMANCE_GATE_FAILED` và chỉ ra render/non-render bottleneck, peak VRAM, slowest shots, cache behavior và projected 20-minute time.

Gate nội bộ: `VP3D_P29_10MIN_ACCEPTANCE_RECORDED`; gate này xác nhận kết quả trung thực, không bắt buộc performance phải pass để có báo cáo hợp lệ.

## 8. Phase 30 — 20-Minute Episode Acceptance

### Target và verdict

20 phút × 24 fps = 28.800 frames; ngân sách tuần tự trung bình khoảng 0,375 giây/frame cho mốc ba giờ. Run phải công bố:

```text
PASS
DEGRADED
BLOCKED_BY_RENDER_THROUGHPUT
```

`PASS` chỉ hợp lệ nếu total wall clock, chất lượng, resolution/fps, hardware và engine đúng contract. Không loại thời gian thất bại/retry khỏi tổng nếu đó là phần production run.

Nếu không đạt, decision package phải so sánh ít nhất: thời gian dài hơn, fps/resolution/quality thấp hơn, hybrid Eevee/Cycles, nâng GPU hoặc chuyển sớm sang Unreal. Mọi thay đổi cần user approval và một acceptance profile mới.

Gate: `VP3D_P30_20MIN_THROUGHPUT_TARGET`.

## 9. Run protocol chung

1. Preflight clean candidate SHA, tool/hardware versions, disk và temperature/power profile.
2. Pin all inputs, approvals, budgets và random seeds.
3. Chạy bằng production orchestrator, không gọi module trực tiếp bằng test harness.
4. Thu telemetry tự động và checkpoint theo node/chunk.
5. Finalizer verify evidence, media, costs/time và derive verdict.
6. Không sửa code/config giữa run rồi nối evidence cũ; thay đổi tạo run ID mới.

## 10. Evidence và rủi ro

Mỗi Phase lưu run manifest, DAG/event receipt, performance/GPU/VRAM profiles, cache/invalidation report, quality/repair report, final media manifest và verdict.

Rủi ro chính là scope/quality drift khi tăng duration. Mỗi acceptance fixture phải khóa scene complexity class, asset-ready assumption, allowed manual actions và quality profile để kết quả các Phase có thể so sánh.
