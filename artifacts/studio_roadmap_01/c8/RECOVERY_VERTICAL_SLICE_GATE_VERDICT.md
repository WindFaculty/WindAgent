# RECOVERY_VERTICAL_SLICE_GATE — C8 verdict

- Contract: studio.contract/v0.1
- Gate: RECOVERY_VERTICAL_SLICE_GATE
- Verdict: **BLOCKED**
- Integration SHA: `026c82c6ea2553054aaef2a7895bbc7534ad7340`
- Evidence SHA-256: `e2fdb97d5a0fabd2b11a8f9cbeb994a9b7662e0ce1f87a952bab2a88d8143686`

## Blockers

- source_worktree_dirty
- c7_evidence_missing

## Evidence policy

- The harness mutates Studio state only through the public V3 API.
- Database reads observe claims, generations and duplicates; no row repair is allowed.
- The only queue operation is an expected-to-fail stale-fence renewal.
- Raw process/test logs stay under `.tmp/studio-c8` or CI artifact storage.

Evidence JSON: `artifacts/studio_roadmap_01/c8/evidence.json`
Generated: 2026-08-11T06:43:06.819426+00:00
