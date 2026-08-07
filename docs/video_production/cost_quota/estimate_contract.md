# Estimate Contract (plan 05 §19.2) — Phase 19

Gate: `VP19_COST_AND_QUOTA_CONTROL_VERIFIED`

## 1. Mục đích

Estimate là đầu vào cho mọi submit: production run phải có estimate trước
khi gửi bất kỳ generation nào. Module:
`orchestration/windagent_orchestration/production/estimator.py`.

## 2. Input

`CreditEstimator.estimate(plan_hash, request_hashes, lines, effective_at)`:

```text
EstimateLine
  provider / model / operation / mode
  duration_seconds
  candidate_count
  reference_generations
  post_production_external
```

## 3. Công thức

```text
rule              = cost_catalog.rule_for(provider, model, operation, mode)
line_cost         = base + per_second * duration
                  × candidate_count  (khi candidate_semantics == "per_candidate")
                  + per_reference × reference_generations
                  + post_production  (khi post_production_external)
estimated_credits = Σ line_cost
retry_reserve     = round(estimated × retry_reserve_ratio)      # mặc định 25%
maximum_credits   = round((estimated + retry_reserve) × contingency)  # mặc định 1.2
requires_approval = maximum >= approval_threshold               # mặc định 100
```

Output JSON (plan 05 §19.2):

```json
{
  "estimated_credits": 200,
  "maximum_credits": 300,
  "candidate_count": 2,
  "retry_reserve": 50,
  "requires_approval": true
}
```

## 4. Fail closed — UNKNOWN

- Bất kỳ line nào thiếu rule trong catalog → toàn bộ estimate có
  `status = "UNKNOWN"` + `unknown_reasons`; **không bao giờ đoán số**.
- Budget policy chặn submit với `BLOCKED_UNKNOWN_ESTIMATE` (§19.4).

## 5. Hash binding & staleness

- `estimate_hash()` = SHA-256 của (schema version, plan_hash,
  request_hashes, catalog_signature, các số liệu, status) — deterministic.
- `is_stale_for(plan_hash, catalog_signature)`: estimate chỉ hợp lệ cho đúng
  plan + catalog lúc tính. Plan đổi hoặc catalog đổi → estimate stale →
  approval cũ stale, phải estimate + approve lại (§19.2).

## 6. Kiểm chứng (verifier)

- `estimate_receipt.json`: phép tính đúng, UNKNOWN khi thiếu rule, hash
  deterministic + thay đổi theo plan/catalog, stale detection.
