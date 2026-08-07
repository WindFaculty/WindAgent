# Quota Ledger Contract (plan 05 §19.3) — Phase 19

Gate: `VP19_COST_AND_QUOTA_CONTROL_VERIFIED`

## 1. Mục đích

Ledger append-only ghi lại toàn bộ lifecycle credit của production run để có
thể reconcile bất kỳ lúc nào, kể cả sau crash/replay. Module:
`orchestration/windagent_orchestration/production/quota_ledger.py`.

## 2. Entry types (append-only)

```text
ESTIMATED        # estimate được ghi nhận
RESERVED         # credit giữ trước khi submit
SUBMITTED        # submit đã xảy ra (kèm external_id)
OBSERVED_DEBIT   # debit thực tế từ provider billing
RELEASED         # credit dự trữ không dùng, trả lại
ADJUSTED         # điều chỉnh (amount có dấu) — bắt buộc reason + source
UNKNOWN          # không xác định được credit state
```

## 3. Luật bất biến

1. **Append-only**: entry không bao giờ bị mutate hoặc xóa; mọi hiệu chỉnh là
   một entry mới (ADJUSTED).
2. **OBSERVED_DEBIT không bao giờ bị overwrite**: một observation trùng
   (cùng dedup_key) là no-op — replay provider result không double-debit.
3. **Replay-safe**: `record()` dedup theo `dedup_key` (default
   `<TYPE>:<request_hash>`) — re-apply outbox/event stream không tạo entry
   thứ hai, không double-reserve/double-debit.
4. **ADJUSTED bắt buộc reason + source**; zero-amount bị từ chối.
5. **OBSERVED_DEBIT bắt buộc source**.
6. Tổng luôn được **derived từ entries** (không có counter mutable), nên
   ledger tự reconcile được chỉ từ entries.

## 4. Công thức

```text
total_reserved      = Σ RESERVED
total_released      = Σ RELEASED
total_observed      = Σ OBSERVED_DEBIT
total_adjusted      = Σ ADJUSTED (signed)
committed           = total_reserved - total_released
balance             = committed - total_observed + total_adjusted
```

## 5. Kiểm chứng (verifier)

- `quota_ledger_receipt.json`: mọi entry type, duplicate observation/reserve
  không double count, crash sau reserve + replay stream → ledger byte-identical,
  adjust yêu cầu reason/source, serialization round-trip.
