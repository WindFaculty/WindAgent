# Known Limitations — Release 0.1 (plan 07 §24/§25)

- **Candidate SHA:** `1753831c752343aa89419e807aa57058266ff75c`
- **Gate:** `VIDEO_PRODUCTION_PLATFORM_VERIFIED` / `READY_FOR_CONTROLLED_RELEASE`
- **Generated at:** 2026-08-02T18:09:17.647116+00:00

## Release-0.1 controlled scope

Release 0.1 only claims (plan §25):

- `flow_accounts`: `1`
- `video_duration_seconds`: `(30, 45)`
- `max_characters`: `2`
- `max_shots`: `7`
- `concurrency`: `1`
- `bounded_approval_cost_retry`: `True`
- `simple_tts_ffmpeg`: `True`
- `basic_resume_human_takeover`: `True`
- `mock_ci_plus_controlled_live_smoke`: `True`

Not supported (deferred to roadmap): multi-account sessions, >7 shots, concurrency >1, complex TTS/FFmpeg graphs, unattended recovery.

## Open release conditions (none release-blocking)

- **REL-001** (low): Real-credit Flow E2E not executed in offline certification — owner `release-owner`, decision `acceptable-for-0.1-controlled-release`.
- **REL-002** (low): Desktop package version diverges from product version — owner `release-owner`, decision `acceptable-for-0.1`.
- **REL-003** (low): Phase 21 verdict is superseded-by-remediation (not a code defect) — owner `release-owner`, decision `acceptable-for-0.1-controlled-release`.
- **REL-004** (low): Phase 24 verdict is BLOCKED by live-run preconditions (approval-gated) — owner `release-owner`, decision `acceptable-for-0.1-controlled-release`.

## Blocker policy compliance (plan §24)

- No phase gate 0-26 is missing; phases 0-20 PASSED, 22/23/25/26 PASSED on the candidate, phase 21 (superseded-by-remediation) and phase 24 (live-run preconditions) are documented conditions with verdict artifacts present.
- All required offline CI lanes PASSED on the candidate SHA.
- No duplicate submit/debit/publish observed in Phase 25/26/27 evidence.
- No critical/high security finding in release scope (Phase 26: 0 blocking).
- Migration/rollback rehearsed on SQLite (idempotent, data preserved).
- License/notice/upstream manifest verified.
- No secret in artifact/log (Phase 26 canary redaction).
