# P0.6 — REVIEW → REVISION → APPROVAL → LOCK (completed)

**Gate:** `P0_6_SCREENPLAY_LOCK_SEMANTICS_VERIFIED` ✅ **ACHIEVED**

**Ngày:** 2026-08-22 · Input: `ban_ke_hoach_v1.md` §P0.6, baseline §2.7

---

## 1. P0.6.1 — Fix semantic `issued_at` (feature correctness)

Bug xác nhận từ baseline (`_lock_inputs`, service.py): receipt issuance time bị **derive từ content hash** (pseudo-time 1970–2037 để fixture determinism). Đã sửa đúng theo plan:

```text
Production : issued_at = actual persisted issuance time (real wall clock)
Test       : inject deterministic Clock qua seam
Không bao giờ derive timestamp từ content hash
```

### Clock seam xuyên suốt đường dispatch thật

Điểm mù lớn nhất: hàm module-level `submit_runnable_nodes()` (đường dispatch DUY NHẤT mà cả start/resume lẫn recovery/reconcile dùng) tự tạo một `StudioRunService` riêng **không có clock** — sửa mỗi class constructor là không đủ. Đã thread `clock` qua toàn chuỗi:

| Seam | File |
|---|---|
| `StudioRunService.__init__(clock=...)` | orchestration/studio/service.py |
| `submit_runnable_nodes(..., clock=...)` (dispatch path) | như trên |
| `StudioCompletionReconciler.__init__(clock=...)` + `_service_submit` | như trên |
| `_submit_runnable_nodes` / `start_or_resume_run` truyền `self._clock` | như trên |
| `StudioComposer.compose_run_service(db, submission, clock=)` | apps/api/composition/studio.py |
| `ApplicationContainer.studio_clock` attribute (test seam) | apps/api/composition/container.py |

- `receipt_id` VẪN content-addressed (`rcpt_{draft_hash[:24]}`) — cùng locked draft cho cùng identity receipt; chỉ `issued_at` trở thành thời điểm phát thật.
- B9 evidence (`produce_b9_evidence.py`) inject `PINNED_CLOCK` (2026-08-11T00:00Z, trùng RECEIPT pin sẵn) và **regenerate** 3 committed chain fixtures — byte-stable qua các lần chạy lại, gate test khớp lại.

## 2. Review là data (verify, đã có từ trước — giữ nguyên)

`ReviewReport` đáp ứng đủ minimum của plan:

```text
findings[]   : code, severity(BLOCKING|WARNING), location, evidence,
               remediation (= suggested correction), source, dimension
dimensions[] : score 0..1 per dimension + blocking flag + note
verdict      : PASS | PASS_WITH_WARNINGS | REVIEW_REQUIRED | FAIL
bounded      : review_iteration + maximum_iterations (policy
               max_review_revision_iterations → revise loop có chặn,
               không autonomous loop vô hạn)
```

## 3. Approval policy + Lock semantics (verify trên đường thật)

- Policies: `AUTO | HUMAN_REQUIRED | QUALITY_GATE_ONLY(=conditional theo quality_thresholds)` — auto-drive tests phủ cả AUTO full-chain lẫn human-rejection → revise → re-review → lock trong CÙNG run.
- Approval command bind revision/checkpoint/artifact_hash/actor/optimistic_version — giữ nguyên (đúng hướng plan).
- Lock PASS chỉ khi: draft+report đúng cặp, hash khớp expected, review requirements thỏa, policy mode cho phép; wrong-hash lock bị từ chối (409) và không mutate gì — vertical lifecycle test asserts 25–29.
- Sau lock: derive revision từ locked parent mà thiếu invalidation intent → `LOCKED_REVISION` 409, revision count không đổi; episode giữ terminal state (vertical test asserts 30–31).

## 4. Code map

| Layer | File |
| --- | --- |
| Fix | `orchestration/windagent_orchestration/studio/service.py` (clock seam 5 chỗ, bỏ hash-derived issued_at) |
| API composition | `apps/api/windagent_api/composition/{studio,container}.py` (+clock param/attr) |
| Evidence | `scripts/verification/produce_b9_evidence.py` (+PINNED_CLOCK, regenerate fixtures) |
| Tests mới | `tests/integration/test_p0_6_lock_semantics.py` |

## 5. Verification

| Suite | Kết quả |
| --- | --- |
| `tests/integration/test_p0_6_lock_semantics.py` — (1) inject pinned clock qua container → receipt artifact persist `issued_at == PINNED` chính xác; (2) không inject → `started ≤ issued_at ≤ finished` (thời điểm phát thật, không phải pseudo-time) | **2 passed** |
| B8/B9 gates + auto-drive + run-service + vertical lifecycle + p05 resume + p04 projects | **50 passed** |
| Full contracts suite | đã chạy sau P0.4/P0.5: 540 passed (không đổi scope P0.6 ngoài fixtures B9) |

Ghi chú trung thực:
- Chain fixtures B9 được REGENERATE với clock pin mới — nội dung thay đổi duy nhất là `issued_at`/hash phái sinh của receipt/package trong fixture (đây chính là hành vi đúng sau fix; giá trị cũ là pseudo-time sai semantic).

## Gate

```text
P0_6_SCREENPLAY_LOCK_SEMANTICS_VERIFIED = ACHIEVED
```

Next: **P0.7 — Frontend product convergence** (episode workspace chuyển từ legacy stub sang `/api/v3/studio/*`, domain Series, provider/model selector đã xong ở P0.3, bỏ fabricate hash).
