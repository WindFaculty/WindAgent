# Circuit Breaker Contract (plan 05 §19.5) — Phase 19

Gate: `VP19_COST_AND_QUOTA_CONTROL_VERIFIED`

## 1. Mục đích

`ProviderCircuitBreaker` mở circuit khi phát hiện tình trạng rủi ro cost /
provider để dừng submit mới cho tới khi reset hợp lệ. Module:
`orchestration/windagent_orchestration/production/circuit_breaker.py`.

## 2. Điều kiện mở circuit

```text
INSUFFICIENT_CREDITS        # credit không đủ
REPEATED_PROVIDER_ERROR     # lỗi provider/account lặp lại đạt threshold
COST_DEVIATION              # observed cost lệch estimate vượt policy ratio
UNKNOWN_CONFIG_OR_COST      # UI/config không xác định được cost
ACCOUNT_CHALLENGE           # account challenge lặp lại
```

## 3. State machine

```text
CLOSED ──(trip)──▶ OPEN ──(cooldown elapsed)──▶ HALF_OPEN ──(probe success)──▶ CLOSED
                     ▲                                                        │
                     └──────────────────(probe failure → OPEN)────────────────┘
HUMAN_RESET / human_review: OPEN/HALF_OPEN ──▶ CLOSED (mọi lúc)
```

## 4. Luật reset — KHÔNG auto-reset liên tục (plan 05 §19.5)

- `maybe_reset()`: chỉ chuyển `OPEN → HALF_OPEN` sau `cooldown_seconds`;
  **không bao giờ tự đóng**.
- `HALF_OPEN` đóng circuit **chỉ khi** một probe thành công
  (`record_success`) hoặc human reset (`human_reset(actor, reason)`).
- `record_success()` reset `consecutive_failures = 0`.
- `record_cost_deviation(observed, estimated)`: mở circuit khi
  `observed / estimated > max_cost_deviation_ratio` (mặc định 1.5);
  `estimated <= 0` → UNKNOWN_CONFIG_OR_COST.

## 5. Determinism & audit

- Mọi transition ghi `CircuitEvent` (state, reason, detail, occurred_at) —
  audit đầy đủ.
- `clock` và `id_fn` injectable (verifier dùng clock cố định + id_fn đếm để
  receipt byte-identical).
- `to_dict`/`from_dict` round-trip đầy đủ (gồm `failure_threshold`).

## 6. Kiểm chứng (verifier)

- `circuit_breaker_receipt.json`: mở trên cả 5 điều kiện, cooldown trước khi
  HALF_OPEN, không auto-close, HALF_OPEN chỉ đóng khi probe success hoặc
  human reset, serialization round-trip.
