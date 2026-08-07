# Release 0.1 Notes

> Kế hoạch 07 §25 (Controlled release) + §28 (Deliverables). Candidate:
> `1753831c752343aa89419e807aa57058266ff75c`.

## Verdict

```text
VIDEO_PRODUCTION_PLATFORM_VERIFIED
READY_FOR_CONTROLLED_RELEASE
```

- Verdict derived từ evidence (không hard-code): `phase_verdict.json` +
  `artifacts/video_production/final/final_verdict.md`.
- Final verdict do `scripts/verification/verify_phase27_release.py` derive trên
  đúng candidate SHA; verifier read-only + deterministic.

## Scope (plan §25)

Release 0.1 chỉ tuyên bố:

- Một Flow account/session/project.
- Video 30–45 giây, tối đa hai character/bảy shot.
- Concurrency 1.
- Bounded approval/cost/retry.
- Simple TTS/FFmpeg.
- Basic resume/human takeover.
- Mock CI + controlled live smoke/E2E.

Không tuyên bố hỗ trợ các mục hoãn trong roadmap (multi-account, >7 shots,
concurrency >1, complex TTS/FFmpeg, unattended recovery).

## What's in this release

- **Post-production pipeline** (Phase 21–24): EDL → render plan → FFmpeg run →
  media verification → deliverable record (được audit: naming collision
  `FinalDeliverable` fixed → `VerifiedDeliverable`; canonical schema lane PASSED).
- **Reliability/chaos certification** (Phase 25): `VP25_RECOVERY_AND_CHAOS_VERIFIED`
  — no duplicate submit/debit/publish, durable state, bounded retry/human state.
- **Security/privacy certification** (Phase 26): `VP26_SECURITY_VERIFIED` —
  SSRF/path traversal/prompt injection/unapproved upload chặn; secret canary
  redaction; 0 release-blocking findings.
- **Release certification** (Phase 27): full CI matrix trên candidate SHA,
  migration rehearsal PASSED, evidence bundle validated.

## Open release conditions (non-blocking findings)

| ID | Title | Severity | Decision |
|---|---|---|---|
| REL-001 | Real-credit Flow E2E not executed offline | low | acceptable-for-0.1-controlled-release (approval-gated) |
| REL-002 | Desktop version diverges (0.6.0 vs 0.3.0) | low | acceptable-for-0.1 |
| REL-003 | Phase 21 verdict superseded-by-remediation | low | acceptable-for-0.1-controlled-release |
| REL-004 | Phase 24 verdict BLOCKED by live-run preconditions | low | acceptable-for-0.1-controlled-release |

Chi tiết: `artifacts/video_production/phase_27/<sha>/open_release_findings.json`
và `artifacts/video_production/final/known_limitations.md`.

## Known limitations

- Controlled real-credit E2E chưa chạy offline (REL-001) — phải chạy theo
  `release_runbook.md` trước lần real-credit đầu tiên.
- PostgreSQL chỉ phủ CI matrix; local rehearsal trên SQLite
  (`migration_and_rollback.md`).
- Desktop version divergence (REL-002).
- Cross-platform (Linux/macOS) chưa certified.

## How to verify

```bash
# Evidence (offline, 0 credit)
python scripts/verification/produce_phase27_evidence.py \
  --candidate-sha 1753831c752343aa89419e807aa57058266ff75c

# Read-only deterministic verification
python scripts/verification/verify_phase27_release.py \
  --evidence-dir artifacts/video_production/phase_27/1753831c752343aa89419e807aa57058266ff75c \
  --candidate-sha 1753831c752343aa89419e807aa57058266ff75c
```

## Owners

- Release owner: `release-owner`
- Security reviewer: `security-reviewer`
- Approver real-credit: `approver`

## Post-release

Theo dõi theo `release_runbook.md` §6 (plan §29). Incident → `incident_response.md`.
