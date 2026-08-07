# Stage B — Blender Runtime

## 1. Kết quả cần đạt

WindAgent có thể phát hiện Blender 4.5 LTS trên Windows, chạy job headless có kiểm soát, tạo `.blend` dẫn xuất, render Cycles thành image sequence, resume/cancel/retry và ghép MP4 bằng FFmpeg. Stage này chưa dùng asset AI, rig phức tạp hay LLM-generated Python.

## 2. Điều kiện đầu vào

- Stage A đã `VERIFIED`; `ProductionEnginePort` và Production IR đã khóa version đầu tiên.
- Blender executable path do cấu hình hoặc detector cung cấp, không hard-code theo máy cá nhân.
- FFmpeg/ffprobe hiện có được probe và ghi version.
- Có temp workspace riêng cho từng job, nằm trong project artifact root đã validate.

## 3. Phase 3 — Blender Runtime Foundation

### Package mục tiêu

```text
tools/windagent_tools/production_engines/blender/
├── runtime/detector.py
├── runtime/capabilities.py
├── runtime/launcher.py
├── runtime/supervisor.py
├── runtime/receipts.py
├── scripts/execute_job.py
└── manifest.py
```

Composition root đăng ký `BlenderEngineAdapter`; core/domain không import package này.

### Backlog

1. `BlenderInstallationDetector`: ưu tiên configured path, sau đó registry/standard locations; trả nhiều candidate có provenance.
2. `BlenderVersionValidator`: chỉ chấp nhận policy-pinned `4.5.x LTS`; mismatch trả typed readiness failure.
3. `BlenderCapabilityProbe`: chạy command read-only để thu build, Python, Cycles devices, import/export và codec capabilities.
4. `BlenderGpuProbe`: phân biệt OptiX/CUDA/CPU, ghi GPU name; không tuyên bố GPU-ready nếu Cycles device chưa thực sự enumerate.
5. `BlenderJobLauncher`: argv dạng list, timeout/cancel token, environment allowlist, workspace validation; không dùng shell interpolation.
6. `BlenderProcessSupervisor`: persist PID/job locator, heartbeat, graceful cancel rồi bounded kill, recovery khi worker restart.
7. `BlenderExecutionReceipt`: lưu exact argv đã redact, version, timing, exit code, hashes và failure classification.
8. Add-on manifest allowlist theo id/version/SHA/source/permissions. Unknown add-on chuyển `REQUIRES_HUMAN_APPROVAL` và job không chạy.

### Kiểm thử

- Detector với configured path, missing path, nhiều version và path có khoảng trắng.
- Capability probe CPU-only, CUDA, OptiX và unexpected output.
- Timeout, cancel, process crash, invalid workspace, malicious argv và stdout không phải UTF-8.
- Restart supervisor reattach hoặc quarantine đúng policy.
- Add-on sai hash/version bị chặn trước process launch.

Gate `VP3D_P3_BLENDER_RUNTIME_VERIFIED` yêu cầu probe thật trên máy baseline và contract tests bằng fake executable trong CI.

## 4. Phase 4 — Blender Deterministic Scene Smoke Test

### Fixture chuẩn

Typed fixture phải mô tả cube, ground, camera, ba lights, một material và keyframed animation. Trusted compiler tạo `scene_plan.json` và script `bpy` cố định theo version; LLM không viết hoặc thực thi Python tùy ý.

### Luồng job

```text
Production IR fixture
→ compile scene plan
→ create/save .blend
→ reopen and inspect .blend
→ render PNG/EXR frame chunks
→ verify every frame
→ FFmpeg assemble
→ ffprobe final MP4
```

### Backlog và acceptance

1. Khóa seed, frame range, fps, color management, resolution, Cycles samples, denoise và device selection.
2. Tách job `COMPILE`, `SAVE`, `INSPECT`, `RENDER_CHUNK`, `ASSEMBLE`, `VERIFY`; mỗi job có idempotency key.
3. Render image sequence bằng atomic temp file → validated final file; không render thẳng MP4 từ Blender.
4. Cancel ở giữa chunk không publish frame dở; resume bắt đầu từ frame hợp lệ tiếp theo.
5. Retry completed job reuse artifact nếu input/config/tool hashes trùng; hash khác phải invalidate.
6. Verify số frame, dimension, decode, duration, video/audio stream policy và output SHA-256.
7. Chạy fixture hai lần với cùng input; metadata/hash cấu trúc phải ổn định. Pixel hash chỉ được yêu cầu nếu hardware/driver/profile giống hệt.

### Evidence

```text
artifacts/video_production_3d/phase_04/
├── scene_plan.json
├── blender_job_receipts/
├── frame_manifest.json
├── ffmpeg_receipt.json
├── ffprobe_receipt.json
├── determinism_report.json
└── phase_verdict.json
```

Gate `VP3D_P4_DETERMINISTIC_RENDER_PASSED` chỉ pass khi create/reopen/render/cancel/resume/retry đều được chứng minh và final MP4 không cần thao tác Blender thủ công.

## 5. Rủi ro và rollback

- Blender/GPU không có trong CI: giữ contract suite bằng fake process và chạy hardware smoke manual/nightly.
- Driver làm pixel output lệch: so sánh scene/config/artifact manifest trước, pixel tolerance theo cùng hardware profile.
- Process còn sống sau worker crash: supervisor/recovery phải reconcile trước khi nhận job mới.
- Stage rollback chỉ gỡ adapter registration; Production IR và evidence không bị xóa.
