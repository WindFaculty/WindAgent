# Video Job Idempotency — Flow Video Generation (Phase 15, plan 04 §23.1)

- **Gate:** `VP15_FLOW_VIDEO_GENERATION_VERIFIED`
- **Module:** `tools/windagent_tools/google_flow/job_record.py` (tái sử dụng
  Phase 14 `FlowJobRegistry`)

## Mục đích

Không có **duplicate submit** trong failure matrix: crash trước/giữa/sau
submit intent, repeated command, job đã tồn tại (completed/active/unknown)
đều được reconcile fail-closed (plan 04 §23.1).

## Durable job model (plan 04 §22)

```json
{
  "generation_id": "...",
  "project_id": "...",
  "revision_id": "...",
  "shot_id": "...",
  "provider": "google_flow_browser",
  "request_hash": "...",
  "submitted_at": "...",
  "browser_session_id": "...",
  "flow_project_id": "...",
  "status": "GENERATING",
  "attempt": 1
}
```

Status: `PREPARED, SUBMITTING, GENERATING, RESULT_READY, DOWNLOADING,
COMPLETED, FAILED_RETRYABLE, FAILED_TERMINAL,
UNKNOWN_REQUIRES_RECONCILIATION, HUMAN_ACTION_REQUIRED, CANCELLED`.

## Reconciliation matrix (§23.1)

```text
lookup request_hash + provider + project mapping
├── COMPLETED                → REUSE_COMPLETED (candidate set intact)
├── active (SUBMITTING/GENERATING/RESULT_READY/DOWNLOADING) → RESUME_ACTIVE
├── UNKNOWN / terminal       → RECONCILE_UNKNOWN (never blind resubmit)
├── FAILED_RETRYABLE + budget → NEW_ATTEMPT (attempt+1, parent link)
└── missing                  → CREATE_PREPARED
```

## Generator thứ tự

1. Mode validation (xem `video_mode_validation.md`).
2. `registry.reconcile(...)`:
   - `REUSE_COMPLETED` → trả outcome `submit_clicked=False`, không tải lại.
   - `RESUME_ACTIVE` → **re-inspect cùng Flow project** (browser close sau
     submit, plan §23.4), không resubmit.
   - `RECONCILE_UNKNOWN` → `FlowVideoSubmitReconciledError`.
   - `NEW_ATTEMPT` → `next_attempt` (generation_id mới `gen_1a2`, attempt+1,
     `parent_generation_id` causal link; receipt cũ không bị ghi đè).
   - ngược lại → `create_prepared` trước submit.
3. Navigate → guard → **persist SUBMITTING intent TRƯỚC click**.
4. Click submit **đúng một lần** với idempotency token.
5. Crash giữa hai bước luôn vào reconciliation.

## Trạng thái COMPLETED (plan 04 §23.3)

- `DOWNLOADING` → acquire từng candidate → `record_candidates` (atomic:
  COMPLETED + candidate_ids) chỉ sau publish thành công.
- Không candidate nào vượt technical validation → `FAILED_TERMINAL` +
  `FlowVideoInvalidResultError` — **không bao giờ COMPLETED với tập invalid**.

## Cancel / retry (plan 04 §23.4)

- `cancel_requested` callback: dừng poll loop cục bộ, mark `CANCELLED`, raise
  `FlowVideoCancelledError` — **không khẳng định** provider-side đã cancel.
- Retry tạo attempt mới, không overwrite receipt cũ.
- Terminal (account/payment/safety) → không auto-retry.
