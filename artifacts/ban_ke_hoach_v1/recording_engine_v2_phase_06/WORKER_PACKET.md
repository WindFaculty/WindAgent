# Phase 6 — WASAPI Microphone

Implement/review `ban_ke_hoach_v1.md` §10 only. Complete the real event-driven WASAPI microphone capture path behind `audio::AudioCapturePort`, preserving the existing single clock/audio packet contracts and no busy polling.

## Authorities to preserve

- `audio/mod.rs::AudioCapturePort` and `EncodedAudioPacket` are the audio port/packet contracts.
- `audio/microphone.rs::WasapiMicrophone` is the sole production mic authority; `audio/device.rs` owns endpoint opening. Reuse, do not introduce a second device or another capture loop.
- Phase 5 `MuxerPort` owns output; do not modify muxer, encoder, capture, service hard cutover, loopback (Phase 7), preview, Tauri, frontend, or previous Phase artifacts.
- Mic stays its native channel count (mono stays mono) then resamples to 48k as necessary; do not fake stereo. Mic mute must affect captured/encoded recorder data, not merely telemetry/UI.

## Work and acceptance

1. Inspect existing audio device/microphone/resampler/AAC code and tests. Implement only real missing Phase-6 behavior: endpoint selection, event-driven IAudioClient/IAudioCaptureClient lifecycle, format negotiation, 48k conversion, discontinuity/silence/device-loss handling, deterministic cleanup, and fail-closed errors.
2. Add focused deterministic tests for channel preservation, 48k output/resampling framing, mute data semantics, state/idempotency/error paths. Any hardware diagnostics must be `#[ignore]` and reported separately.
3. Run relevant audio tests and `cargo check`; run a real microphone probe only if safely noninteractive and record actual device/result. Do not fabricate hardware evidence.
4. Write `EVIDENCE.md`, `PHASE_06_REPORT.md`, and `phase_06_verdict.json` in this folder with exact evidence classification and formal verdict. Hardware permission/device availability gates must remain BLOCKED/NOT_VERIFIED as appropriate.
5. Do not commit/reset/clean/ask questions or start Phase 7.
