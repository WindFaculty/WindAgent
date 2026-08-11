# RELEASE_CANDIDATE_GATE — C6 verdict

- Contract: studio.contract/v0.1
- Gate: RELEASE_CANDIDATE_GATE
- Verdict: **PASS**
- Integration SHA: `bf8b1407dfe0b9cd68b6a1c7195fa508625e70d6`

## Checks

- PASS — checkers_green
- PASS — desktop_vitest_green
- PASS — desktop_build_green
- PASS — tauri_release_binary_present
- PASS — bundle_scan_clean
- PASS — source_scan_clean
- PASS — v2_api_regression_green
- PASS — session_recovery_green
- PASS — studio_security_redaction_green
- PASS — studio_contracts_consumer_green
- PASS — no_unknown_failures
- PASS — full_matrix_only_known_failures
- PASS — ci_studio_job_wired

## Scope

- Desktop version aligned to canonical 0.3.0 (package.json, tauri.conf.json,
  Cargo.toml, Cargo.lock, package-lock.json); version consistency checker PASS.
- V2 events contract fixed: /api/v2/events canonical surface + legacy
  /api/v2/video-production/events retained, websocket /ws stream added;
  the A7-known events-contract failures are retired.
- Session recovery WS 403 retired: events websocket streams recorded
  envelopes per aggregate with heartbeat pings.
- Desktop matrix: vitest 142, tsc + vite build, Tauri release binary.
- Bundle/source scans clean (no fixture IDs, dev endpoints, secrets,
  mock fallback).
- Full workspace matrix cross-checked against artifacts/ci/c6_junit.xml;
  remaining failures are A7-classified pre-existing outside Plan C.
- CI: studio-roadmap-gates job added and wired into final-evidence.

Evidence JSON: `artifacts/studio_roadmap_01/c6/evidence.json`
Generated: 2026-08-11T04:31:53.511509+00:00
