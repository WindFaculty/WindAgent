# Phase 5 — Native MKV / libavformat

## Mission

Implement or complete the real native `LibavMuxer` path required by `ban_ke_hoach_v1.md` §9.  It must mux the Phase-4 encoded H.264/HEVC packets into independently playable, segmented MKV files using libavformat APIs — never an FFmpeg CLI recorder.

Phase 4 is implementation-ready after repair: its raw driver output is Annex-B, while its session packet contract is intentionally 4-byte length-prefixed for avcC/hvcC.  PTS zero is valid and Phase-4 packet PTS is monotonic when B-frames are disabled.  Phase 4's 30-minute soak remains an unresolved production gate but does **not** block this phase's implementation contract.

## Existing authority and contracts — preserve

- `muxer/mod.rs::MuxerPort` is the only muxer port: `prepare`, `open_segment`, `stage_video_extradata`, `stage_audio_extradata`, `write_packet`, `close_segment`, `finalize_take`.
- `muxer/libav.rs::LibavMuxer` is the native production implementation; `libav_loader.rs::LibavRuntime` owns dynamically loaded libav function pointers. Do not introduce a second loader/runtime, an FFmpeg subprocess, or a mock in production.
- `encoder::EncodedPacket` supplies `data`, `pts_us`, `dts_us`, `is_keyframe`, and `codec`.  Its length-prefixed video packet data plus staged avcC/hvcC extradata must be consumed correctly by the MKV stream.
- Segment semantics: `.tmp` → write → trailer → flush → fsync → atomic rename `.mkv`; no arbitrary boundary: caller requests IDR, finishes current GOP, then closes.  Each finalized segment must be independently playable.
- Existing unrelated worktree edits and Phase-3/4 scope must remain untouched.  Do not modify service hard cutover, capture, encoder, audio, preview, Tauri, frontend, roadmap, or unrelated artifacts.

## Required implementation/review work

1. Inspect `muxer/libav.rs`, `libav_loader.rs`, `tracks.rs`, `muxer/mod.rs`, relevant tests, and existing service integration before editing. Reuse correct existing code; fill only real gaps.
2. Ensure native runtime path uses the appropriate libavformat lifecycle: output context allocation, streams and codec parameters, custom/existing AVIO handling as needed, header after staged extradata, interleaved writes with correctly rescaled PTS/DTS/duration/keyframe flags, trailer, close, flush/fsync, atomic rename. All FFI structures/functions must be versioned and error-checked.
3. Enforce fail-closed state behavior: no write before segment/header/extradata, reject missing/invalid runtime, duplicate/open-index regression, invalid track/codec/packet/timestamp, and do not publish a partial `.mkv` as finalized after failures.
4. Preserve monotonic timestamp rules per track.  Zero PTS is valid.  Do not silently reorder or fabricate timestamps. B-frame decode order must be handled through DTS/PTS semantics if supported; if current V2 contract rejects B-frames, make that explicit and test it.
5. Validate 1+ real produced MKV segment through `ffprobe` (or an equivalent installed libav probe) when runtime is available. Record actual command/output: valid Matroska container, H.264/HEVC stream, FPS metadata (where applicable), monotonic timestamps, and no corrupt tail. If runtime/ffprobe cannot be safely available, report exact blocker rather than simulating success.
6. Add focused tests for state/order, timestamp zero/monotonicity, extradata handshake, keyframe flags, segmentation finalization and fail-closed paths. Run the relevant Rust tests and `cargo check`.
7. Create/update only `artifacts/ban_ke_hoach_v1/recording_engine_v2_phase_05/{EVIDENCE.md,PHASE_05_REPORT.md,phase_05_verdict.json}` with baseline SHA, exact commands/results, change list, classifications (`OBSERVED`, `STATICALLY_VERIFIED`, `NOT_VERIFIED`), limitations, and truthful verdict.

## Acceptance boundaries

- You may make scoped implementation repairs and tests in `apps/desktop/native/recording-engine/src/muxer/**` and directly necessary shared muxer contract files only.
- Do not claim real libav/ffprobe validation from mock output. Do not count ignored/manual tests as standard test passes.
- Do not commit, reset, clean, ask questions, or start Phase 6.
- At most one complete implementation pass. Return a concise self-review: changed files; what is complete; tests/probes run; remaining gates; and whether formal PASS is justified.
