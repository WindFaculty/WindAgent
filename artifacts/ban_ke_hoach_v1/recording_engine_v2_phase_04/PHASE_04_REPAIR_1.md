# Phase 4 — Repair Pass 1: zero PTS must remain valid

## Observed defect (independent acceptance probe)

`production_encode_texture_probe` on the real NVENC path (lookahead=32, B-frames=0) emitted its first packet with `picPts=516646`, followed by packets with `picPts=16666`, `33332`, … .  This is non-monotonic and violates the Phase 4/5 timestamp contract.

The source cause is in `NvencSession::lock_packets`: `NV_ENC_LOCK_BITSTREAM.output_time_stamp == 0` is treated as absent and replaced by the current-call fallback PTS.  Zero is a valid PTS for the first encoded frame.

## Scope and acceptance contract

1. Preserve NVENC's `output_time_stamp` exactly, including zero.  Do not use a nonzero test to infer timestamp validity.
2. If a fallback is genuinely required by an API-defined unavailable state, represent that state explicitly; never conflate it with timestamp zero.  Keep PTS/DTS rules compatible with the existing `has_b_frames` logic.
3. Add a focused regression test.  Prefer extending the ignored real-hardware probe to assert emitted PTS are nondecreasing and include `0`; also add a deterministic unit test for any pure timestamp-selection helper introduced.
4. Re-run and record exact commands/results:
   - `cargo test --manifest-path apps\\desktop\\native\\recording-engine\\Cargo.toml encoder:: --lib`
   - `cargo check --manifest-path apps\\desktop\\native\\recording-engine\\Cargo.toml`
   - `cargo test --manifest-path apps\\desktop\\native\\recording-engine\\Cargo.toml production_encode_texture_probe --lib -- --ignored --nocapture`
   - `cargo test --manifest-path apps\\desktop\\native\\recording-engine\\Cargo.toml session_lifecycle_probe --lib -- --ignored --nocapture`
5. Correct `EVIDENCE.md`, `PHASE_04_REPORT.md`, and `phase_04_verdict.json`: the previous run was a first-pass failure for PTS monotonicity.  Do not claim PTS correctness until the repaired probe demonstrates it.

## Constraints

- Limit changes to Phase 4 encoder/tests/artifacts.  Do not alter WGC, muxer, service contracts, roadmap, or unrelated worktree edits.
- Preserve the real direct D3D11 texture → NVENC path and mapping cleanup fix.
- Distinguish raw NVENC Annex-B output from the session's intentional conversion to length-prefixed packets for the MKV contract.
- Do not commit, reset, clean, ask questions, or start later phases.

## Completion report

State changed files, test output summaries, the observed repaired PTS sequence, remaining hardware/soak gates, and any uncertainty.  A successful repair does not satisfy the Phase 4 30-minute no-stall gate.
