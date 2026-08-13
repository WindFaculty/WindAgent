# C7 Provider Reliability — Forensic Diagnosis (attempt 8)

Thư mục: `artifacts/studio_roadmap_01/c7/provider_reliability_diagnostic/`
Thời điểm audit: sau attempt 8 (run `run_cff7ff8fbebc4007`), trước mọi mutation.

## 1. Tóm tắt

C7 = FAIL / BLOCKED với blocker khai báo `PROVIDER_RELIABILITY`. Audit cho thấy:
đây chỉ là TRIGGER. Root cause chính là **defect lifecycle của WindAgent**:
runtime không có deadline nào cho run/task, và khi deadline của certification
harness (45 phút) hết hạn, launcher giết process trong khi run vẫn RUNNING —
không có finalizer, không reconciler, không recovery nào đóng run. Kết quả:
zombie `RUNNING` tồn tại trong DB. Lặp lại 2 lần liên tiếp (gemma31b-5 và
gemma31b-6).

```
PRIMARY_ROOT_CAUSE = RUNTIME_TIMEOUT_RECONCILIATION_DEFECT
TRIGGER           = PROVIDER_RELIABILITY (một generation mất 40m34s)
CONFIDENCE        = 0.95
```

## 2. Attempt 8 — dòng thời gian (UTC)

| T | Sự kiện |
|---|---------|
| 16:49:30.8 | Harness khởi động (`versions.generated_at`) |
| 16:49:32.4 | API process start (pid 5668) |
| 16:49:33.7 | Worker start (pid 16352); API giành recovery leader lease (expire 16:50:03) |
| 16:49:36.1 | Run `run_cff7ff8fbebc4007` tạo (10-node DAG) |
| 16:49:36.2 → 16:52:14.6 | idea.generate, idea.evaluate, bible.generate, beats.generate: SUCCEEDED, mỗi call < 1 phút, POST 200 OK |
| 16:52:15.1 | outline.generate claimed (stsk_7a3da288d1c5), POST bắt đầu |
| 16:53:16.5 | Lần RENEW lease cuối của outline (hết hạn 16:53:46). Renew dừng suốt 40 phút còn lại (anomaly — xem §5) |
| **17:32:49.2** | **outline.generate SUCCEEDED — HTTP 200 sau 40m34s. Một attempt duy nhất, zero timeout, zero retry (route_attempts_v3)** |
| 17:32:51.3 | Harness approve OUTLINE; screenplay.generate claimed (stsk_f9744f96e90e), POST bắt đầu |
| **17:34:32** | **Deadline harness 45 phút hết hạn** (`c7_slice_harness.py:658` → raise SliceError `:750`) |
| 17:34:35.1 | Heartbeat cuối của worker (lease còn active) |
| **17:34:37.7** | Launcher terminate api + worker (exit 1). Không finalize, không reconcile. Evidence ghi nhận FAIL |

Hậu quả trong DB (read-only):
- `studio_runs.status = RUNNING` (updated_at không đổi từ lúc tạo — zombie)
- `studio_run_nodes[screenplay.generate] = DISPATCHED`
- `execution_leases[stsk_f9744f96e90e] = active` (tự hết hạn 17:35:05, không chủ)
- `task_runs[stsk_f9744f96e90e] = running`
- `cancellation_requests = []` — không có cancellation nào

## 3. Câu trả lời cho các câu hỏi chính

**A. Provider request** — Đã gửi. 4 POST trước đó 200 OK nhanh; POST outline
200 OK sau 40m34s (PROVIDER_SLOW thật: server-side latency, client không lỗi).
Request ID không được capture (`provider_request_id = null` mọi nơi). Call
screenplay in-flight 106s khi bị giết — thời lượng không giới hạn.

**B. Deadline ownership** — 45 phút chỉ tồn tại ở certification layer
(`c7_slice_harness.py:658`). Runtime KHÔNG có deadline: field
`StudioTaskEnvelope.deadline` tồn tại (models.py:146) nhưng **luôn null** và
không nơi nào đọc. `TimeoutEvaluator` chỉ dùng cho retry policy.
HTTP client có cap 300s/read (endpoint_adapter_resolver.py:41) nhưng không
chặn tổng thời lượng (call 40m34s vẫn thành công) — cap này chỉ theo chunk.

**C. Cancellation** — `CANCELLATION_REQUESTED = NO`, `ACKNOWLEDGED = NO`.
Bảng cancellation rỗng. Runtime cancel là cooperative no-op giữa các phase
(`studio_runtime.py:232`). Provider request bị bỏ chỉ bằng kill process
(TCP reset); phía Google có thể vẫn tiếp tục generate.

**D. State machine** — Run chỉ chuyển trạng thái qua
`StudioCompletionReconciler.handle_task_result` khi có task result. Worker
chết giữa generation → không có result → không transition nào. Không có
timeout transition. `StudioCompletionRecovery` chỉ replay reconciler cho
completion đã terminal (crash window finalize→reconcile), không đóng run
RUNNING cũ. Recovery leader lease hết hạn 16:50:03, không ai giành lại.

## 4. Vì sao `PROVIDER_RELIABILITY` là sai làm blocker duy nhất

Case C theo quy tắc quyết định:

```
Google generation > 45m (thực tế: 40m34s + call thứ 2 chưa xong)
+ WindAgent để run RUNNING sau deadline (bằng chứng DB)
→ PRIMARY_ROOT_CAUSE = RUNTIME_TIMEOUT_RECONCILIATION_DEFECT
  TRIGGER = PROVIDER_RELIABILITY
```

Điều kiện "provider reliability thật" (WindAgent phát hiện deadline, chuyển
run đúng về terminal state) KHÔNG thoả: hệ thống không có cơ chế nào phát
hiện deadline ở runtime. Kết luận PROVIDER_RELIABILITY thuần tuý trong
final_verdict.json cũ là chưa đầy đủ.

## 5. Anomaly phụ (chưa giải thích được từ artifact)

- Lease renewal của task outline **dừng** lúc 16:53:16 dù worker cấu hình
  heartbeat 5s (`runner.py:48`) và worker_registrations vẫn được update.
  Không có warning nào trong worker.stderr.log. Leased expired 16:53:46
  trong khi task chạy tới 17:32:49. Không ảnh hưởng kết cục attempt này
  (chỉ một worker tồn tại), nhưng là lỗ hổng ownership tiềm ẩn.
- `route_attempts_v3` ghi `started_at` sau `finished_at` (skew nhỏ trong log).

## 6. Patch (tối thiểu, sau khi matrix hoàn thành)

Mục tiêu: *không provider call nào được để C7 attempt ở RUNNING sau deadline
authoritative.*

| File | Thay đổi |
|------|----------|
| `orchestration/.../studio/service.py` | `run_deadline()`: deadline tuyệt đối = run.created_at + budget (env `WINDAGENT_STUDIO_RUN_DEADLINE_SECONDS`, default 2700s). Envelope giờ mang `deadline`. Run-relative (không per-task) để chain task dài không thể vượt deadline. |
| `apps/worker/.../studio_runtime.py` | Code `STUDIO_RUN_DEADLINE_EXCEEDED`. Trước khi chạy handler: deadline đã qua → fail ngay. Khi chạy: `asyncio.wait_for(handler, remaining)` — hết hạn → cancel coroutine → provider request bị bỏ (httpx aclose trong finally), task FAILED. |
| `scripts/.../certification_launcher.py` | `WINDAGENT_STUDIO_RUN_DEADLINE_SECONDS=2550` (42.5 phút < 45 phút harness) → run terminalize trước khi harness giết process. |
| `tests/unit/worker/test_studio_run_deadline.py` | 8 test mới (mới) |

Không đổi: model Google, quality threshold, prompt, retry budget, deadline
harness.

Chuỗi sau fix:
```
RUNNING → task vượt deadline → wait_for hủy provider call → task FAILED
→ reconciler → retry (nếu còn budget, fail nhanh vì deadline đã qua)
→ budget hết → run FAILED (terminal) → harness thấy terminal state
```

Late-result fencing: task timeout xong, coroutine bị cancel — result muộn
không bao giờ tới runner; finalize dùng CAS + fencing token; test e2e chứng
minh run không thể bị "sống lại" thành COMPLETED sau restart.

## 7. Verification

- ruff: clean (4 file).
- Test mới: 8 passed (hàng provider 5s, deadline 0.4s — không chờ 45 phút).
- Regression: `test_studio_runtime.py` + `test_studio_c8_c9_certification.py`
  = 65 passed; worker + orchestration = 231 passed (1 fail CÓ SẴN, verified
  trên HEAD sạch, không liên quan); `tests/unit/scripts/` = 94 passed.

## 8. C7 rerun — điều kiện

READY_FOR_CONTROLLED_C7_RERUN = YES (đã chứng minh bằng targeted tests).
Chưa tự chạy attempt 9. Lệnh/điều kiện cho lần chạy mới:

```bash
# 1. Source sạch (stash/commit mọi thứ kể cả evidence mới)
git status --short   # phải rỗng ngoài artifacts
# 2. Rotate GOOGLE_API_KEY trước (key cũ lộ qua ?key= thời S4.2)
# 3. Chạy đúng entry hiện có:
python scripts/studio_roadmap/c7_slice_harness.py   # (hoặc entry launcher chuẩn của cert flow)
# 4. Kiểm chứng sau khi chạy (bất kể PASS/FAIL):
#    - studio_runs.status ∈ {COMPLETED, FAILED, CANCELLED, REVISION_REQUIRED}
#    - KHÔNG còn run RUNNING trong candidate DB
#    - Nếu FAIL: fail phải kèm error code chuẩn (STUDIO_RUN_DEADLINE_EXCEEDED
#      hoặc provider failure có retry), không phải "last RUNNING"
```

Điều kiện dừng cũ (S2): C8/C9 = NOT_RUN khi C7 không PASS.

## 9. Đề xuất ngoài phạm vi (chưa làm)

- Coordinator in-endpoint transient backoff/retry (4/8 attempts chết vì 503
  đơn lẻ — vẫn là vấn đề provider thật, độc lập với defect lifecycle này).
- Stale-run reconciler chạy định kỳ (đóng run RUNNING không chủ khi worker
  chết hẳn, không phải chỉ tại worker startup).
- Điều tra lease renewal dừng giữa generation dài.
- `provider_request_id` capture từ header để đối chiếu request phía Google.
