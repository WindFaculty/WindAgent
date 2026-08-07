# Stage K — Quality Review

## 1. Kết quả cần đạt

Quality pipeline chặn lỗi rẻ trước render, phát hiện lỗi kỹ thuật/thẩm mỹ sau render và tạo repair plan nhỏ nhất có thể. Một score tổng hợp không được che blocking defect; retry luôn gắn với nguyên nhân và invalidation scope.

## 2. Điều kiện đầu vào

- Stages F–J xuất manifest typed cho scene, track, render profile, frame và provenance.
- Reviewer media hiện có được giữ và mở rộng thay vì tạo pipeline tách rời.
- Artifact dependency graph có thể xác định output nào phụ thuộc camera, asset, animation, facial hoặc render profile.

## 3. Phase 22 — 3D Technical Reviewer

### Pre-render gates

Tạo deterministic checks cho missing object/texture, broken rig, frame range, camera/character collision, lighting, audio timing, unapproved asset/add-on và VRAM budget. Blocking finding dừng render submission.

### Post-render gates

1. Verify frame count, decode, dimension, black/corrupt frames và missing ranges.
2. Detect flicker/noise/exposure discontinuity theo temporal windows.
3. Review identity, lip-sync, occlusion, continuity, motion quality, lighting và camera compliance bằng deterministic metrics trước, VLM/vision model sau.
4. Cross-shot comparison luôn pin character/location/lighting continuity references.
5. Mỗi finding gồm code, severity, affected entity/frame range, evidence, confidence và suggested repair scope.
6. Confidence thấp hoặc creative conflict chuyển human review; không auto-pass.

### Verdict rule

```text
blocking finding tồn tại  → REJECT
không blocking, low confidence → REQUIRES_HUMAN
mọi required dimension pass → APPROVE
```

Gate nội bộ: `VP3D_P22_TECHNICAL_REVIEW_VERIFIED`.

## 4. Phase 23 — Intelligent Retry

### Components

```text
FailureClassifier
RepairPlanner
InvalidationPlanner
RetryBudgetPolicy
RepairExecutionReceipt
```

### Backlog

1. Map finding sang owner: asset, rig, scene, camera, lighting, body animation, facial, render hoặc post-production.
2. Chọn smallest repair unit: facial track, camera compile, asset revision, affected animation, frame range hoặc audio mix.
3. Tạo repair input revision mới và dependency invalidation; không sửa artifact locked.
4. Dedupe cùng failure signature; giới hạn attempt/cost/time và phát hiện repair loop.
5. Sau repair, chạy lại tất cả checks liên quan và downstream checks, không chỉ check từng fail.
6. Escalate human khi cùng failure lặp, confidence thấp, cần creative choice hoặc vượt budget.

Gate nội bộ: `VP3D_P23_INTELLIGENT_RETRY_VERIFIED`.

## 5. Test matrix

- Missing texture → asset repair; camera collision → camera recompile; lip-sync → facial only; noise → affected frames.
- Một defect có nhiều nguyên nhân khả dĩ phải giữ uncertainty, không tự chọn khi confidence dưới ngưỡng.
- Repair không invalidates unrelated approved shots.
- Duplicate event/restart không chạy cùng repair hai lần.
- Retry loop và budget exhaustion chuyển human/block đúng policy.
- Reviewer/VLM timeout không biến thành PASS.

## 6. Evidence

```text
artifacts/video_production_3d/phase_22..23/
├── deterministic_findings.json
├── temporal_review.json
├── cross_shot_review.json
├── review_verdict.json
├── failure_classification.json
├── repair_plan.json
├── invalidation_receipt.json
└── retry_execution_receipt.json
```

Fixture phải có defect cấy chủ động để chứng minh không false PASS.

## 7. Rủi ro

- Reviewer model có thể không ổn định; model/version/prompt hash và confidence calibration phải được pin.
- Repair quá rộng làm mất cache và tăng render time; invalidation tests là gate bắt buộc.
- Metric kỹ thuật không thay thế creative approval; human review vẫn là authority ở trường hợp mơ hồ.
