# Stage J — Rendering

## 1. Kết quả cần đạt

WindAgent render Cycles theo profile versioned, chặn scene vượt VRAM trước khi launch và phục hồi ở cấp frame chunk. Output là image sequence đã verify cùng đầy đủ receipt; hệ thống không đổi sang Eevee ngoài quyết định rõ của người dùng.

## 2. Điều kiện đầu vào

- Scene/camera/light/body/facial tracks đã compile và preflight.
- Blender capability probe xác nhận Cycles device trên máy baseline.
- Artifact store hỗ trợ content-addressed immutable output và atomic publish.
- Xác định headroom VRAM theo phép đo baseline, không chỉ theo thông số GPU danh nghĩa.

## 3. Phase 19 — Cycles Production Renderer

### Profiles

Tạo `PREVIEW`, `FINAL`, `FINAL_HIGH` với settings versioned: engine, device, resolution, fps, samples, adaptive threshold, denoise, bounces, motion blur, color management và output format. `FINAL` mặc định là Cycles.

### Backlog

1. Compile `RenderIntent` trung lập thành `BlenderRenderProfile` trong adapter.
2. Probe OptiX/CUDA/CPU và record actual device Blender dùng; fallback CPU cần explicit policy/verdict.
3. Áp adaptive sampling, denoise, instancing, persistent data khi đo được lợi ích, LOD, light/transparent bounce budget và texture/geometry limits.
4. Render image sequence PNG hoặc EXR; lựa chọn format nằm trong profile và post-production contract.
5. Pin seed, film/color settings và dependency hashes; cache key gồm scene/shot/frame/profile/Blender/device class.
6. Thu telemetry theo frame/chunk: render seconds, samples, peak memory nếu lấy được, device và failure.
7. Preview và final artifacts không dùng chung key; preview không thể được promote thành final chỉ bằng đổi metadata.

Gate nội bộ: `VP3D_P19_CYCLES_RENDERER_VERIFIED`.

## 4. Phase 20 — VRAM Budget Manager

### Components và policy

```text
SceneResourceEstimator
VramBudgetPolicy
TextureBudgetPolicy
GeometryBudgetPolicy
VramMitigationPlanner
```

Baseline policy ban đầu:

```text
SAFE     < 6.0 GB estimated
WARNING  6.0–7.0 GB
BLOCK    > 7.0 GB
```

Các ngưỡng phải cấu hình và hiệu chỉnh bằng measured peak VRAM.

### Backlog

1. Estimate textures, geometry, modifiers, volumes, render buffers và acceleration structures; ghi uncertainty.
2. So sánh estimate với actual trên fixtures để hiệu chỉnh safety factor.
3. Mitigation theo thứ tự có kiểm soát: texture downscale → LOD → instancing → hidden geometry removal → split shot.
4. Mọi mitigation tạo derived scene/profile revision và quality impact report; không mutate silent.
5. Nếu vẫn vượt hard limit, block trước render với recommendation, không crash/retry mù.

Gate nội bộ: `VP3D_P20_VRAM_BUDGET_VERIFIED`.

## 5. Phase 21 — Fault-tolerant Render Jobs

### Job model

```text
episode → scene → shot → frame chunk
```

Mỗi chunk pin scene/shot/profile/asset hashes, frame start/end, Blender/GPU, attempt và output hashes.

### Backlog

1. Scheduler chọn chunk size theo measured render time và recovery overhead.
2. Reserve idempotency key trước side effect; chỉ một worker sở hữu chunk bằng lease/fencing token.
3. Frame publish atomic; 0-byte, undecodable hoặc sai dimension không được coi completed.
4. Worker crash/restart reconcile PID, lease và frame manifest; resume từ frame hợp lệ tiếp theo.
5. Stale worker không được publish sau khi lease chuyển owner.
6. Retry classification phân biệt OOM, Blender crash, bad asset, timeout, disk full và user cancel.
7. OOM kích hoạt mitigation/replan; deterministic bad asset không retry vô ích.

Gate nội bộ: `VP3D_P21_RENDER_RECOVERY_VERIFIED`.

## 6. Test matrix và evidence

- CPU/GPU selection, unsupported backend và actual-device mismatch.
- Scene dưới/cận/trên budget; estimate-vs-actual calibration.
- Kill Blender/worker giữa chunk, duplicate dispatch, lease expiry, stale completion và disk full.
- Corrupt/missing frame, wrong hash, changed render profile và partial retry.
- Cache reuse chỉ khi toàn bộ input hashes khớp.

Evidence bắt buộc gồm render profile, resource estimate, mitigation plan, frame/chunk manifests, raw performance telemetry, recovery receipt và final verdict theo từng Phase.

## 7. Rủi ro hiệu năng

Target cuối `0,375 giây/frame` có thể không thực tế với Cycles cho scene production. Stage này chỉ cung cấp số đo và tối ưu có chứng cứ; không được làm giảm chất lượng hoặc đổi engine ngoài policy để tạo PASS giả.
