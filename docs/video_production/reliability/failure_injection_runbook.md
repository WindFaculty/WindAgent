# Failure-Injection Runbook

Phase 25 (plan 07 §7–§8) — how to run the mandatory chaos matrix and how the
harness arms/disarms injections safely.

## 1. Harness contract (plan §7)

The harness (`scripts/verification/chaos_phase25.py`) must:

- select an injection point by scenario/workflow/action id — each scenario has
  a fixed `scenario_id` (CH01…CH15) and a documented injection point;
- arm/disarm clearly — injection happens inside an isolated temp workdir per
  scenario; nothing is injected into production state;
- scope to the test project/session only — all scenarios use `vp_chaos` /
  `vp_soak` / `vp_deleted` synthetic projects and mock browser sessions;
- enforce a run timeout — each scenario runs in-process with bounded loops;
- save pre-state/post-state — every receipt records `pre_state` and
  `post_state`;
- auto-collect DB/event/job/artifact/cost evidence — receipts record run
  state, outbox events, job registry status and ledger entries;
- verify cleanup — `cleanup_verified` and the soak leak check assert no
  `.tmp`/leftover files;
- never run destructive commands on a wide workspace.

## 2. How to run

```bash
# 1. Produce evidence (runs all 15 scenarios + soak at mock/integration level)
python scripts/verification/produce_phase25_evidence.py \
    --candidate-sha <40/64-hex>

# 2. Verify (read-only, derives VP25_RECOVERY_AND_CHAOS_VERIFIED)
python scripts/verification/verify_phase25_reliability.py \
    --evidence-dir artifacts/video_production/phase_25/<candidate_sha> \
    --candidate-sha <candidate_sha>

# 3. Write CLI-contract fixtures (temp dir only)
python scripts/verification/fixture_phase25_reliability.py --out-dir /tmp/fix
```

## 3. Mandatory scenario matrix (plan §8)

| Scenario | Injection point | Expected behavior | Receipt |
|---|---|---|---|
| CH01 Kill worker khi provider generating | Sau submit đã xác nhận | Lease hết, worker mới reconcile cùng job, không resubmit | CH01_WORKER_KILL_GENERATING |
| CH02 Kill browser sau submit | Job active | Workflow pause/recover, reattach/inspect | CH02_BROWSER_KILL_AFTER_SUBMIT |
| CH03 Mất mạng | Navigation/poll/download | Bounded retry, state durable, không click submit lại | CH03_NETWORK_LOSS |
| CH04 Session hết hạn | Trước hoặc sau submit | Human login required, safe resume | CH04_SESSION_EXPIRY |
| CH05 Selector thay đổi | Trước action quan trọng | Drift/error fail closed, không coordinate click | CH05_SELECTOR_DRIFT |
| CH06 Download 0 byte | Candidate download | Reject/quarantine, retry download trong budget | CH06_DOWNLOAD_ZERO_BYTE |
| CH07 Không có video stream | Technical review | Candidate reject, job không hoàn tất giả | CH07_NO_VIDEO_STREAM |
| CH08 Insufficient credits | Pre/after submit UI state | Circuit open, workflow pause, ledger reconcile | CH08_INSUFFICIENT_CREDITS |
| CH09 CAPTCHA | Bất kỳ browser step | Human CAPTCHA required, zero bypass | CH09_CAPTCHA |
| CH10 User cancel | Pending/active generation | Dừng schedule, reconcile external truth | CH10_USER_CANCEL |
| CH11 Database restart | Transaction/outbox | Atomicity và replay idempotent | CH11_DATABASE_RESTART |
| CH12 Duplicate event | Event ingestion | Một state transition/ledger effect | CH12_DUPLICATE_EVENT |
| CH13 Lease expiry | Worker đang giữ step | Stale write bị reject | CH13_LEASE_EXPIRY |
| CH14 Stale worker write | Sau reassignment | Optimistic version/lease chặn | CH14_STALE_WORKER_WRITE |
| CH15 External project bị xóa | Navigation/recovery | Terminal/manual decision, không tự thay project | CH15_FLOW_PROJECT_DELETED |

## 4. Reproducibility

Injections are deterministic at mock level (real orchestration machinery +
injected provider/browser fakes). Every receipt carries input/output hashes
so a re-run can be compared. Scenarios that can only be performed manually
require an equivalent runbook with observable assertions (the receipts above
document the observed assertions).

## 5. Safety

- Chaos tests never touch production data/accounts.
- All workdirs are temp; the producer removes its scratch dir.
- ffprobe/ffmpeg are required for CH06/CH07 (fail closed when missing).
