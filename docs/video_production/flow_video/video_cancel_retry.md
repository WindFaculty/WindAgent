# Video Cancel / Retry — Flow Video Generation (Phase 15, plan 04 §23.4)

- **Gate:** `VP15_FLOW_VIDEO_GENERATION_VERIFIED`
- **Module:** `tools/windagent_tools/google_flow/video_generation.py`

## Mục đích

Cancel và retry phải đúng ngữ nghĩa: cancel **dừng cục bộ** action/poll mà
**không khẳng định** provider-side đã cancel nếu UI không chứng minh; retry
tạo **attempt mới** có causal link, không overwrite receipt cũ; lỗi
account/payment/safety là terminal, không tự retry (plan 04 §23.4).

## Cancel

- `cancel_requested: Callable[[], bool] | None` được inject từ composition
  root.
- Generator kiểm tra callback:
  - **Trước submit**: cancel → `FlowVideoCancelledError`, không click gì.
  - **Trong poll loop** (mỗi vòng): cancel → mark `CANCELLED`, raise
    `FlowVideoCancelledError` với message rõ ràng *"provider-side
    cancellation is not asserted"*.
- Không bao giờ gửi thêm action sau cancel; job để ở `CANCELLED` để
  reconcile xử lý (RECONCILE_UNKNOWN — không blind resubmit).

## Retry

- `FAILED_RETRYABLE` + budget chưa cạn → reconcile trả `NEW_ATTEMPT`.
- Generator gọi `registry.next_attempt(parent_id)`:
  - `generation_id` mới (`gen_1a2`), `attempt = parent.attempt + 1`;
  - `parent_generation_id` giữ causal link (plan 04 §18.4);
  - receipt cũ (candidate_ids, submitted_at) **không bị ghi đè**.
- Budget cạn → `RECONCILE_UNKNOWN` — không resubmit mù.

## Terminal policy

- `FAILED_TERMINAL` (account/payment/safety, error state, invalid result)
  → reconcile `RECONCILE_UNKNOWN`; không tự retry.
- Browser/session failure SAU submit → ưu tiên **re-inspect cùng Flow
  project** (`RESUME_ACTIVE`), không tạo submit mới.

## Fail-closed guarantees

- Cancel = local stop; message ghi rõ không assert provider-side.
- Retry = attempt mới + causal link; không mất dữ liệu cũ.
- Terminal = không auto-retry; mọi đường đều qua reconcile.
