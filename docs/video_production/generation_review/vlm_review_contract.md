# VLM Review Contract (plan 05 §25.2, §24) — Phase 20

Gate: `VP20_GENERATION_REVIEW_VERIFIED`

## 1. Mục đích

`VlmReviewer` (`intelligence/windagent_intelligence/video/reviewers/vlm.py`)
là **tier thứ hai** của reviewer hierarchy (plan §24): chạy **chỉ sau**
deterministic gate. Provider-neutral: model đi qua `ReviewModelPort` (Protocol
— adapter inject tại composition), module không bao giờ import provider.

## 2. Phạm vi

Chấm 8 dimension VLM từ structured intent + approved references:

```text
prompt_compliance, identity_consistency, location_consistency,
prop_consistency, motion_quality, camera_compliance,
dialogue_alignment, visual_artifacts
```

Output hợp lệ là JSON object với mỗi dimension:
`{score: 0..1, confidence: 0..1, evidence: [...]}` + model/prompt version.

## 3. Fail-closed (gate condition 3)

**Không bao giờ tạo false PASS.** Tất cả các trường hợp sau đều là
`REVIEW_ERROR` (blocking defect với code `REVIEW_ERROR`):

- timeout;
- response rỗng;
- output không phải JSON hợp lệ;
- JSON không phải object;
- thiếu/vô hiệu dimension;
- score hoặc confidence ngoài 0..1.

`passed` của mỗi dimension tính theo `config_for(dimension).pass_threshold` —
không hardcode 0.5.

## 4. Hierarchy (gate condition 1)

Pipeline chỉ gọi VLM khi `det.technical_valid = True`. Deterministic failure
(decode / thiếu stream) → VLM bị skip hoàn toàn, defect blocking deterministic
đảm bảo verdict REJECT.

## 5. Kiểm chứng (verifier)

- `vlm_review_receipt.json`: payload hợp lệ → đủ 8 dimension + passed theo
  threshold; timeout/empty/invalid JSON/schema violation/score out-of-range →
  `review_error = True` + defect `REVIEW_ERROR`; async path khớp sync; model
  không được gọi khi deterministic fail.
