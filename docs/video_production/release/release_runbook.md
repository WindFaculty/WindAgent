# Release Runbook — Release 0.1

> Kế hoạch 07 §26 (Operational runbook) + §27 (Final certification sequence).
> Candidate: `1753831c752343aa89419e807aa57058266ff75c` · Gate:
> `VIDEO_PRODUCTION_PLATFORM_VERIFIED` / `READY_FOR_CONTROLLED_RELEASE`.

## 1. Mục đích

Runbook này mô tả trình tự vận hành để phát hành có kiểm soát Release 0.1: từ
verify candidate sạch, chạy CI matrix, rehearsal migration, chạy controlled
real-credit E2E (điều kiện release), cho tới khi issue final verdict.

**Verdict PASSED tại Phase 27 là offline certification** — nó chứng nhận
platform + CI + evidence. Controlled real-credit E2E (REL-001) vẫn là điều kiện
bắt buộc trước lần chạy real-credit đầu tiên.

## 2. Trước khi phát hành (pre-flight)

1. **Backup/migration plan**: snapshot database + browser/session test profile;
   xem `migration_and_rollback.md`.
2. **Browser runtime/profile setup**: Chrome installed; profile dir tách biệt,
   encrypted at rest (Phase 26 policy — `docs/video_production/security/`).
3. **Flow login/takeover procedure**: chỉ human login; CAPTCHA không bypass.
4. **Credit/budget configuration**: đặt credit maximum và circuit-breaker
   threshold trước bất kỳ real-credit run nào.
5. **Health checks**: chạy `/healthz` API, worker lease sanity, queue depth 0,
   no stale worker.
6. **Artifact storage/retention**: kiểm tra quota, retention policy, cleanup job.
7. **Known UI assumptions**: ghi lại selector/flow version đang nhắm tới.

## 3. Final certification sequence (plan §27)

```text
1. Verify clean candidate SHA        → candidate_attestation.json (HEAD == candidate, worktree sạch)
2. Run complete PR CI matrix         → ci_run_manifest.json (all lanes PASSED)
3. Run migration/rollback rehearsal  → migration_rehearsal_receipt.json
4. Run Phase 25 regression           → scripts/verification/verify_phase25_reliability.py
5. Run Phase 26 regression           → scripts/verification/verify_phase26_security.py
6. Approve real-credit maximum       → REL-001 approval gate (human)
7. Run controlled E2E + browser recovery → release_e2e_receipt.json (mock) + live runbook
8. Verify final media/cost/traceability → ffprobe final MP4 hash + cost ledger reconcile
9. Build and hash release artifacts  → build_hash_manifest.json
10. Validate evidence bundle         → evidence_validation_receipt.json + evidence_manifest.json
11. Review known limitations/open risks → open_release_findings.json (0 release-blocking)
12. Issue final verdict              → phase_verdict.json PASSED + READY_FOR_CONTROLLED_RELEASE
```

Reproduce certification (offline, không tốn credit):

```bash
# 1. Tạo evidence (chạy tất cả lanes thật)
python scripts/verification/produce_phase27_evidence.py \
  --candidate-sha 1753831c752343aa89419e807aa57058266ff75c

# 2. Verify read-only (deterministic)
python scripts/verification/verify_phase27_release.py \
  --evidence-dir artifacts/video_production/phase_27/1753831c752343aa89419e807aa57058266ff75c \
  --candidate-sha 1753831c752343aa89419e807aa57058266ff75c
```

## 4. Controlled real-credit E2E (điều kiện release — REL-001)

Chỉ thực hiện khi **đã được phê duyệt** credit maximum + Flow session:

1. Chốt creative brief lock, credit maximum, timing (plan §17 — phase 24 preconditions).
2. Chạy theo `scripts/verification/runbook_phase24_e2e.py` / phase-24 runbook.
3. Ghi project/job ID đã sanitize, cost ledger reconcile, final MP4 hash vào
   `artifacts/video_production/final/real_flow_e2e_receipt.json`.
4. Xác nhận `final_verdict.md` conditions: credit max, Flow auth, human takeover.

## 5. Rollback / disable (plan §26)

- Feature flag/composition option để ngừng Flow provider (không xóa evidence).
- Active run được pause/reconcile trước khi disable.
- Không downgrade database nếu không an toàn — xem `migration_and_rollback.md`.
- API/provider port vẫn tồn tại để future provider.

## 6. Post-release observation (plan §29)

Theo dõi: browser/session health, selector drift, generation success/failure/retry,
duplicate prevention, human-action frequency, cost estimate-vs-observed, candidate
rejection reasons, recovery time, final media verification, storage growth.

Incident có nguy cơ duplicate cost / account safety / secret leak / corrupt artifact
→ mở circuit/disable provider trước khi run mới. Xem `incident_response.md`.

## 7. Blocker checklist (plan §24)

Trước khi ghi `READY_FOR_CONTROLLED_RELEASE`, xác nhận **không có**:

- [ ] phase gate 0–27 chưa pass (evidence lineage hợp lệ — phase 21/24 là
      documented BLOCKED, không phải blocker)
- [ ] required CI job fail/missing trên candidate SHA
- [ ] duplicate submit/debit/publish chưa giải quyết
- [ ] final E2E không truy vết hoặc vượt budget
- [ ] critical/high security finding trong release scope
- [ ] migration/rollback chưa chứng nhận
- [ ] license/notice/third-party manifest sai
- [ ] secret trong artifact/log
- [ ] known limitation mâu thuẫn support claim
- [ ] final evidence validation fail

Chủ sở hữu: `release-owner`. Mọi lệnh real-credit trong runbook phải có người
phê duyệt và ghi lại approver + timestamp.
