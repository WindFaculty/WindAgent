# Budget Policy Contract (plan 05 §19.4) — Phase 19

Gate: `VP19_COST_AND_QUOTA_CONTROL_VERIFIED`

## 1. Mục đích

`GenerationBudgetPolicy` là **SINGLE gate** mà mọi provider submit path phải
đi qua (plan 05 §21 — "mọi submit path đi qua reserve/approval policy").
Module: `orchestration/windagent_orchestration/production/budget_policy.py`.

## 2. Luật

1. **Không submit nếu credit state hoặc estimate UNKNOWN** (fail closed).
2. **Reserve trước submit; reconcile sau observed result** — reserve/reconcile
   là 2 call tách biệt để engine commit atomic cùng run state (§8.3).
3. **Retry chỉ khi còn retry budget** (`RetryBudget`).
4. **Candidate count bị chặn** (`candidate_limit`).
5. **Quality / high-cost mode cần approval gắn estimate hash**; plan/catalog
   đổi → approval stale, không được tái sử dụng (§19.2).
6. **Daily / monthly / project / run limits áp dụng trước provider call**
   (`DailyLimit`, `MonthlyLimit`, `ProjectLimit`, `run_limit_credits`).
7. **PoC không submit nhiều generation song song** (`max_parallel_submits`).

## 3. Submit verdicts

```text
ALLOWED
BLOCKED_UNKNOWN_ESTIMATE        # estimate UNKNOWN — fail closed
BLOCKED_UNKNOWN_CREDIT_STATE    # không có balance
BLOCKED_STALE_APPROVAL          # estimate stale (plan/catalog đổi)
BLOCKED_APPROVAL_REQUIRED       # cần approval đúng estimate hash
BLOCKED_RETRY_BUDGET
BLOCKED_CANDIDATE_LIMIT
BLOCKED_DAILY_LIMIT
BLOCKED_MONTHLY_LIMIT
BLOCKED_PROJECT_LIMIT
BLOCKED_RUN_LIMIT
BLOCKED_INSUFFICIENT_CREDITS
BLOCKED_PARALLEL_SUBMIT
```

Thứ tự kiểm tra (fail closed trước): UNKNOWN estimate → credit state →
stale → approval → retry → candidate → daily/monthly/project/run → parallel →
credits. Boundary chính xác (`used + amount <= max`) được ALLOW.

## 4. Reserve & reconcile

```python
policy.reserve(run_id, request_hash, estimate)        # RESERVED = maximum_credits
policy.reconcile(run_id, request_hash, observed,      # OBSERVED_DEBIT | UNKNOWN
                 external_id, source)
```

Cả hai idempotent theo dedup_key — crash sau reserve rồi replay outbox không
double-reserve; replay provider result không double-debit (§19.3).

## 5. Kiểm chứng (verifier)

- `budget_policy_receipt.json`: unknown fail closed, approval đúng estimate
  hash (hash khác → không hợp lệ), retry/candidate bounded, exact boundary +
  vượt daily/monthly/project/run limit, insufficient credits, parallel bound,
  reserve→reconcile không double count.
