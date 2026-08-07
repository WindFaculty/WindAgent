# Stage O — Production Hardening

## 1. Kết quả cần đạt

Blender/add-on execution được quản trị fail-closed, một shot có thể tái tạo từ manifest đầy đủ và Google Flow không còn residue trong runtime/config/test/docs authority. Đây là điều kiện bắt buộc trước controlled release của pipeline Blender.

## 2. Điều kiện đầu vào

- Golden/multi-minute E2E đã cung cấp attack surface và reproducibility fixtures thật.
- Stage N đã xác định cách nhận `.blend` do người dùng sửa.
- Security, redaction, artifact validation và audit nền của WindAgent vẫn hoạt động.

## 3. Phase 33 — Security & Add-on Governance

### Backlog

1. Manifest allowlist ghi add-on id/version/SHA/source/license/permissions/approved actor/time và compatible Blender version.
2. Discovery chỉ tạo quarantine record; install/enable/update/remove là destructive/privileged action cần approval.
3. Blender launcher dùng isolated config/profile, tắt auto-run scripts và chỉ mở workspace/asset path đã validate.
4. Scan `.blend`, Python, archive, mesh, texture và Geometry Nodes external dependency; chặn path traversal/symlink escape/network call ngoài policy.
5. Network/domain/file/subprocess permissions theo job; add-on không được kế thừa credential WindAgent.
6. Redact logs/manifests/screenshots và audit mọi override/approval.
7. Threat-model supply chain, malicious asset, prompt-to-code, resource exhaustion, DLL/Python import hijack và tampered executable.
8. Add negative security suite và incident quarantine/runbook.

Gate nội bộ: `VP3D_P33_BLENDER_SECURITY_VERIFIED`.

## 4. Phase 34 — Reproducibility

### Manifest bắt buộc

```text
WindAgent SHA, schema/compiler versions, Blender/build/Python,
trusted script/add-on hashes, asset/animation/audio hashes,
voice/TTS/alignment versions, render settings/seeds/device,
FFmpeg/ffprobe version, manual overrides và approvals
```

### Backlog

1. Tạo `ProductionReproducibilityManifest` và canonical hash/schema.
2. Export dependency closure cho một shot; missing artifact hoặc unknown version làm replay fail-closed.
3. Replay trên cùng profile và so scene manifest, frame/media technical properties và hashes/tolerance policy.
4. Phân biệt bit-exact, functionally equivalent và non-reproducible; không dùng một boolean mơ hồ.
5. Tạo archival bundle/restore test; external provider artifact phải được lưu hoặc có immutable reference policy.

Gate nội bộ: `VP3D_P34_REPRODUCIBILITY_VERIFIED`.

## 5. Phase 35 — Full Flow Purge Certification

### Audit scope

Kiểm tra imports, runtime composition, schemas, config/env, credentials, tests/fixtures, scripts, UI/API, current docs và package/dependency manifests. Historical artifacts/docs được phép chỉ trong archive có label rõ và không được load/ship.

### Backlog

1. Tạo machine-readable forbidden-symbol/path catalog và exceptions hẹp cho purge checker.
2. Chạy static scan + import graph + built wheel/package content + Web/Desktop bundle/config scan.
3. Chứng minh application boot, full tests và golden smoke không cần Flow credential/browser runtime.
4. Xóa secret entries và migration path an toàn; không log giá trị credential khi purge.
5. Lưu zero-count report theo category và negative fixture chứng minh checker bắt residue mới.

Gate: `GOOGLE_FLOW_FULLY_RETIRED`.

## 6. Evidence và release gate

```text
artifacts/video_production_3d/phase_33..35/
├── addon_allowlist_snapshot.json
├── security_test_matrix.json
├── threat_model_report.json
├── reproducibility_manifest.json
├── replay_comparison.json
├── flow_purge_report.json
├── package_content_report.json
└── phase_verdict.json
```

Stage O pass khi P33–P35 verified trên cùng candidate SHA, no open Critical/High finding, purge checker chạy trong CI và replay một golden shot đạt policy.

## 7. Rủi ro

- Chuỗi Flow trong archive gây noise; exception chỉ được phép theo exact archived path.
- Add-on native binary khó sandbox hoàn toàn trên Windows; default deny và approval không thay thế isolation.
- Reproducibility pixel-perfect có thể lệch do driver/hardware; policy phải ghi rõ comparison class, không hạ tiêu chuẩn sau khi chạy.
