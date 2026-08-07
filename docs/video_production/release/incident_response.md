# Incident Response — Release 0.1

> Kế hoạch 07 §26 (Rollback/disable) + §29 (Post-release observation).
> Release 0.1 chỉ claim basic resume/human takeover; incident phải fail closed.

## 1. Nguyên tắc

Mọi incident có nguy cơ **duplicate cost, account safety, secret leak hoặc
corrupt artifact** phải **mở circuit/disable provider trước khi tiếp tục run
mới**. Không "chạy tiếp và quan sát" với các loại incident này.

## 2. Phân loại severity

| Severity | Ví dụ | Hành động |
|---|---|---|
| CRITICAL | Duplicate debit/submit/publish, secret leak, corrupt artifact publish | Disable provider ngay, open circuit, human triage |
| HIGH | Recovery loop, credit vượt budget, downloader SSRF | Pause active run, reconcile, chờ quyết định |
| MEDIUM | Selector drift, session expiry, 0-byte download | Bounded retry, human CAPTCHA/login, drift report |
| LOW | Slow navigation, UI text thay đổi không ảnh hưởng action | Ghi finding, theo dõi |

## 3. Runbook theo loại

### 3.1 Duplicate submit/debit/publish (CRITICAL)

1. Mở circuit-breaker / disable Flow provider (feature flag/composition option).
2. Không xóa evidence; pause + reconcile các run đang active.
3. Kiểm tra cost ledger + event/outbox replay idempotency (Phase 25 invariants).
4. Ghi incident ID + observed duplicate; mở finding nếu chưa có.

### 3.2 Secret leak / canary trong log/event/screenshot (CRITICAL)

1. Ngừng run mới; isolate evidence bundle.
2. Xác định canary (Phase 26 redaction test) hoặc raw secret.
3. Redact/rotate secret; cập nhật redaction policy; regression test.

### 3.3 Real-credit E2E vượt budget (HIGH)

1. Pause workflow; circuit open.
2. Reconcile cost ledger so với credit maximum đã duyệt (REL-001).
3. Không tự resubmit; cần human approval để tiếp tục.

### 3.4 Recovery không đúng (HIGH)

- Không suy `COMPLETED` chỉ vì file tồn tại (plan §9.2 reconciliation order).
- Kiểm tra durable intent → provider state → artifact → event → ledger → workflow.

## 4. Disable/rollback (plan §26)

- Feature flag/composition option để ngừng Flow provider — không xóa
  project/artifact evidence.
- Active run được pause/reconcile.
- Không downgrade database nếu không an toàn — xem `migration_and_rollback.md`.
- API provider/future provider port vẫn tồn tại.

## 5. Post-incident

- Ghi incident ID, trigger, detection/recovery time, data loss allowed, cleanup
  verification vào artifact evidence (Phase 25 receipts).
- Incident không reproducible được phân loại flaky/observability gap, không đóng
  finding (plan §9.4).

## 6. Liên hệ

- Release owner: `release-owner` (quyết định disable/circuit).
- Security reviewer: `security-reviewer` (secret/privacy incident).
- Người phê duyệt real-credit test: `approver` (budget/payment incident).
