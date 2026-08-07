# Cross-shot Continuity Contract (plan 05 §25.3, §24) — Phase 20

Gate: `VP20_GENERATION_REVIEW_VERIFIED`

## 1. Mục đích

`CrossShotReviewer`
(`intelligence/windagent_intelligence/video/reviewers/cross_shot.py`) là
**tier thứ ba** của reviewer hierarchy: so candidate với predecessor/successor
**thông qua continuity ledger Phase 10** (gate condition 5 — cross-shot review
dùng continuity ledger, không đoán từ candidate đơn lẻ).

## 2. Nguồn dữ liệu

Đọc `ContinuityLedgerReceipt` (Phase 10): ledger entries (incoming/required/
outgoing state) + `blocking_issues`. Reviewer không tự sinh continuity.

## 3. Luật (plan §25.3)

1. **Ledger blocking issues → typed blocking defect**: mỗi
   `ContinuityIssueCode` được map sang `BlockingReasonCode` chuẩn:
   `PROP_UNEXPLAINED_CHANGE → PROP_MISMATCH`, `CAMERA_SIDE_VIOLATION →
   CAMERA_SIDE_VIOLATION`, `IDENTITY_HASH_MISMATCH → IDENTITY_MISMATCH`,
   `CHANGE_OUTSIDE_ALLOWED / PARALLEL_CONFLICT / MISSING_REQUIRED_STATE →
   CONTINUITY_VIOLATION`.
2. **Predecessor.outgoing → successor.incoming consistency**: field
   `camera_side` phải khớp giữa 2 shot kề (screen direction sống trên shot
   SPECIFICATION, không nằm trong ledger state nên chỉ so camera_side).
3. **Required tail/head frame relation**: successor yêu cầu `reference:*` phải
   khớp outgoing reference của predecessor; lệch → `TAIL_HEAD_FRAME_RELATION`.

Mọi blocking defect mang typed reason code + evidence (gate condition 2).

## 4. Pipeline

`ReviewPipeline` chỉ chạy cross-shot khi ledger được cung cấp
(`ledger_receipt is not None`) — khi có ledger thì cross-shot **bắt buộc**.

## 5. Kiểm chứng (verifier)

- `cross_shot_receipt.json`: ledger sạch → continuity_valid; flip camera_side
  giữa predecessor→successor → `CAMERA_SIDE_VIOLATION`; ledger blocking issue
  → typed defect; tail/head reference lệch → `TAIL_HEAD_FRAME_RELATION`;
  pipeline không chạy cross-shot khi không có ledger.
