# Phase 5 — Repair 1: preserve valid B-frame timestamps

The incomplete first implementation added `validate_packet_contract` and rejects every `packet.dts_us != pts_us` as `MKV_BFRAMES_UNSUPPORTED`.

This is not acceptable: `VideoConfig.b_frames` is an exposed V2 configuration and `NvencSession` has explicit B-frame DTS logic.  The native muxer already passes both fields through `AVPacket` and `av_packet_rescale_ts`; do not silently remove a supported profile feature.

Required repair:

1. Replace the blanket `DTS == PTS` rejection with correct validation for B-frame-capable packets: zero PTS remains valid; PTS must be nondecreasing in presentation order for each track; decode timestamps must be valid for the muxer/timebase and monotonic in the order written (not fabricated or silently rewritten).  Preserve input PTS and DTS to `AVPacket` then rescale together.
2. Track the correct per-slot state necessary to enforce the above.  Do not use a global maximum that masks regressions.  Explain the written-order vs presentation-order distinction in evidence.
3. Add focused deterministic tests for valid zero PTS, valid non-equal B-frame DTS/PTS that remains accepted, and rejected PTS/DTS regressions/invalid packet cases.
4. Fix/remove any misleading comments that claim V2 disables B-frames.
5. Run at least the muxer test module and `cargo check`; run a real libav/ffprobe validation only if the local runtime supports it. The prior `ffprobe` result on a mock `.tmp` file is not valid evidence and must be marked NOT_VERIFIED, not PASS.
6. Finish all required Phase-5 evidence artifacts. State plainly that no actual libav runtime means Phase 5 cannot receive formal PASS.

Scope stays `src/muxer/**` plus Phase-5 artifacts. Do not touch Phase 3/4/6+, service/capture/encoder, or unrelated worktree changes. Do not commit/reset/clean.
