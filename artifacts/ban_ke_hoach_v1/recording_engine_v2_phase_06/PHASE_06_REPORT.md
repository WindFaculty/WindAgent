# Phase 6 — WASAPI Microphone

**Roadmap:** ban_ke_hoach_v1.md §10 (recording-engine V2)
**Baseline commit:** `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` (branch `refactor/architecture-v3-hardening`)
**Generated:** 2026-08-28T23:55:00+07:00
**Verdict:** `PASS` — Phase-6 microphone contract satisfied (event-driven WASAPI, format negotiation, 48k resample framing, mono preservation, mute data semantics, discontinuity/silence/device-loss fail-closed, deterministic cleanup, 41 audio / 144 total tests PASS, real mic exercised). Hardware permission/device-loss chaos and inherited libav ffprobe remain NOT_VERIFIED per packet (not Phase-6 scope).

## 1. Mission

Implement/review `ban_ke_hoach_v1.md` §10 only: complete the real event-driven WASAPI microphone capture path behind `audio::AudioCapturePort`, preserving the existing single clock/audio packet contracts and no busy polling. Authorities: `AudioCapturePort`/`EncodedAudioPacket` are the port/packet contracts; `WasapiMicrophone` is the sole production mic authority and `audio/device.rs` owns endpoint opening with no second device or capture loop; Phase-5 `MuxerPort` owns output and must not be touched (no muxer, encoder, capture, service hard cutover, loopback, preview, Tauri, frontend changes); mic stays native channels (mono stays mono) then resamples to 48k; mute must affect captured/encoded recorder data, not merely telemetry/UI.

## 2. Baseline and scope

Baseline `0f869d16` preserved. Pre-existing dirty work preserved (notably `capture/wgc.rs` Phase-3, `encoder/nvenc_session.rs` + `mod.rs` Phase-4 zero-PTS, `muxer/libav.rs` Phase-5 B-frame DTS). This phase touches only `apps/desktop/native/recording-engine/src/audio/**` and strictly necessary test additions. `artifacts/ban_ke_hoach_v1/phase_03`, `phase_04`, `recording_engine_v2_phase_05` were not modified.

Existing primitives reused: `audio/mod.rs::AudioCapturePort` (prepare/start/stop/poll_block/set_muted/is_available/track) + `PcmBlock`/`EncodedAudioPacket`/`TrackKind`, `audio/device::wasapi::StreamHandle` (shared event-driven core), `audio/aac::MfAacEncoder` + `linear_resample`/`PtsBook`/`AAC_OUTPUT_SAMPLE_RATE`, `audio/microphone::WasapiMicrophone` wrapper, `audio/loopback::WasapiLoopback` left untouched (Phase-7).

## 3. What was already correct, incomplete, and what this pass added

| Component | Status | Details |
|-----------|--------|---------|
| `audio/device.rs` — WASAPI core | **Correct** | `IMMDeviceEnumerator → IMMDevice (capture) → IAudioClient(SHARED\|EVENTCALLBACK, 100ms) → IAudioCaptureClient` with `CreateEventW`/`SetEventHandle`, worker `WaitForSingleObject(100ms)` heartbeat → `GetNextPacketSize` loop → `GetBuffer`→`pcm_packet_to_f32`→`ReleaseBuffer`, `COM MTA` guard, `FORMAT probe_from_tags` (PCM/IEEE_FLOAT/EXTENSIBLE), `AUDCLNT_BUFFERFLAGS_SILENT`→zeros, `AUDCLNT_E_DEVICE_INVALIDATED`→mark unavailable+last_error, 128-block VecDeque oldest-drop with `overflow_dropped`, `Drop` joins worker + `CloseHandle`. No busy polling. |
| `audio/microphone.rs` — WasapiMicrophone | **Correct** | Thin wrapper: `prepare` drops prior stream then `open_microphone_stream(device_id)` (empty→default capture via eMultimedia/eCommunications, else exact ACTIVE id), `start` → `StreamHandle::start`, `stop` idempotent, `poll_block` drains one block, `set_muted` stores atomic, `is_available` from shared flag, `last_error`/`overflow_dropped` for telemetry. Fail-closed. |
| `audio/aac.rs` — resample/PTS/encode | **Correct** | `f32_to_s16_clamped` (NaN→0), `linear_resample` ceil-scaled per-channel, `compensated_frame_count` + `linear_resample_scaled` (±25ppm threshold), `PtsBook` anchor ring (presentation vs written-order, silence-gap restart), `MfAacEncoder::new` validates 1–2 channels + non-zero rate + 32k–512k bitrate, locked 48k/1024-frame output, mono `output_channels` preserved, `build_aac_asc` for 48k mono/stereo. |
| Endpoint/format/48k/mute/lifecycle | **Correct, now with extra deterministic coverage** | All §10 bullets were already implemented; this pass adds **8 hardware-free deterministic tests** to lock them: mono channel preservation, 48k framing within 1 frame across 44.1/32/96k, mute data semantics (silent flag + mock mute), state/idempotency (prepare→available, start without prepare fails, unknown id rejected, stop idempotent, mute toggles, PcmBlock framing, DeviceInfo defaults, TrackKind mapping). |
| `audio/loopback.rs` | **Correct, untouched** | Separate Phase-7 authority; not modified per packet. |
| Hardware diagnostics | **Already #[ignore] where applicable** | NVENC probes 5 ignored; audio hardware-dependent `default_device_round_trip_when_present` etc. are not #[ignore] but degrade gracefully (skip when no hardware, typed error when unknown id) — per packet, no new #[ignore] hardware test was needed beyond existing ones. |

No duplicate loader/runtime, no second mic device, no new capture loop, no FFmpeg subprocess, mock remains dev-only.

## 4. Focused deterministic tests added

**In `audio/aac.rs`:**

- `phase6_mono_stays_mono_no_fake_stereo` — mono 1024 → s16 2048 bytes (stereo would be 4096), identity resample keeps 1024, 44.1k→48k mono length ceil(1024*48000/44100) within 1, ASC accepts 1ch+2ch, ch 6 correctly rejected with `AAC_UNSUPPORTED_CHANNEL_COUNT`.
- `phase6_output_is_locked_to_48k_resampling_framing_within_one_frame` — for mono+stereo at 44.1k/48k/32k/96k, resampled length within 1 output frame (≈1 sample mono, 2 stereo); asserts `AAC_OUTPUT_SAMPLE_RATE==48000` and `AAC_FRAME_FRAMES==1024`.
- `phase6_mute_data_semantics_preserves_frames_and_pts` — silent-flag packet yields exact-length zeros; muted-zeroed f32 → s16 zeros; frame count preserved.

**In `audio/mod.rs` (new `phase6_tests` module):**

- `pcmblock_frames_respects_channel_count` — 960 stereo→960 frames, 480 mono→480, 0ch→0.
- `mock_mute_affects_captured_data_not_only_telemetry` — MockAudioCapture unmuted carries signal, muted delivers exact-length all-zero samples preserving channels, unmute restores signal (muted data = recorder data, not meter).
- `mock_state_and_idempotency_before_and_after_prepare` — poll before start None, prepare→is_available+track, start/stop idempotent, mute toggles not panicking.
- `wasapi_device_info_defaults_are_fail_closed` — default `available false`, channels 0, rate 0.
- `track_kind_maps_to_muxer_tracks` — `Mic→TrackId::Mic`, `System→TrackId::System`.

All 8 are hardware-free and counted in the 41 audio / 144 total.

## 5. Authorities and invariants — verified

| State | Authority | Evidence |
|-------|-----------|----------|
| Audio port contract | `audio/mod.rs::AudioCapturePort` + `PcmBlock`/`EncodedAudioPacket` | Trait unchanged; `WasapiMicrophone`/`WasapiLoopback` implement identical lifecycle |
| Mic endpoint opening | `audio/device.rs::wasapi` (ComGuard, resolve_endpoint, open, StreamHandle) | Sole opener; microphone.rs never duplicates |
| Mic production track | `audio/microphone.rs::WasapiMicrophone` | Sole Phase-6 prod authority |
| 48k output | `audio/aac::AAC_OUTPUT_SAMPLE_RATE`=48000, `MfAacEncoder::output_sample_rate` | Locked, validated; resample always before encode |
| Mono preservation | `FormatProbe.channels` + `linear_resample` per-channel + `MfAacEncoder` channel check | New mono test + `asc_matches` |
| Mute data | `SharedState::muted` zeroed in worker, Mock zeroed in poll | New mute tests |
| Clock | `clock::qpc_now` used for every `PcmBlock.qpc` (§12) | device.rs worker stamps QPC |
| Non-invariants (untouched) | muxer (libav), encoder (NVENC), capture (WGC/D3D11), service hard cutover, loopback (Phase-7), preview, Tauri, frontend | Diff shows only `audio/aac.rs`+`audio/mod.rs` test additions |

Non-negotiable invariants — all hold (STATICALLY_VERIFIED + OBSERVED):

- No second WASAPI device or capture loop; mic and system audio remain separate tracks (Principle E).
- Event-driven capture: WaitForSingleObject on client's event, no busy loop.
- Mix format captured native then resampled to 48k; mono never faked to stereo.
- Packet conversion preserves QPC-derived PTS continuity through silence; never mass-drops frames (§12).
- Every device/endpoint/format/start failure typed UPPER_SNAKE; unknown ids never substituted.
- Bounded queue (128) drops oldest with honest `overflow_dropped` telemetry; lifecycle prepare→start→poll→stop→Drop joins.

## 6. Failure, idempotency, concurrency

- WASAPI objects are agile (free-threaded marshaler); `StreamHandle: Send` (IAudioClient/IAudioCaptureClient + HANDLE + atomics); worker does its own `CoInitializeEx(MTA)`. `AacEncoderPort: Send`. No global mutable audio state.
- `prepare` after `prepare` drops prior worker before opening new (re_prepare test).
- `start` without `prepare` → `MIC_NOT_PREPARED`; `start` twice → `WASAPI_ALREADY_STARTED`; `stop` before `prepare` idempotent Ok; `poll_block` before start → None; `unknown device_id` → `WASAPI_DEVICE_NOT_FOUND` (not substituted) — all deterministic.
- Repeated `set_muted` never panics; toggles zero samples in place preserving frame counts.
- No durable state, DB, retry ledger introduced.

## 7. Tests and gates — exact results

| Gate | Command | Result | Classification |
|------|---------|--------|----------------|
| cargo check | `cargo check --manifest-path apps\desktop\native\recording-engine\Cargo.toml` | PASS (0 errors) | OBSERVED |
| audio filtered | `cargo test --manifest-path apps\desktop\native\recording-engine\Cargo.toml --lib audio -- --test-threads=1 --nocapture` | **41 passed, 0 failed** (includes 3 new aac + 5 new mod tests + real encode round-trip with PTS log) | OBSERVED |
| full lib | `cargo test --manifest-path apps\desktop\native\recording-engine\Cargo.toml --lib -- --test-threads=1` | **144 passed, 0 failed, 5 ignored** (ignored = NVENC driver probes) | OBSERVED |
| wasapi pure (format/silent/truncated) | `cargo test --lib audio::device::wasapi::tests -- --test-threads=1` | **7 passed** (extensible float, PCM16/float tags, unsupported fail-closed, f32/i16 round-trip, silent zeros, truncated reject, degrade without hardware) | OBSERVED |
| hardware probe (noninteractive, real) | `cargo run --bin probe_temp` (temporary, then removed) → `wasapi_available=true, mic_available=true, system_available=true, aac_available=true, input_endpoints=1, render_endpoints=1` + `audio::microphone::tests::default_device_round_trip_when_present` exercised real start/stop/drain (well-formed blocks, no panic) | **PASS (OBSERVED, no fabrication)** | OBSERVED |
| unknown device rejection | `cargo test --lib audio::microphone::tests::unknown_device_id_is_rejected_not_substituted` → `WASAPI_DEVICE_NOT_FOUND` | PASS | OBSERVED |
| lifecycle fail-closed | `cargo test --lib audio::microphone::tests::lifecycle_fails_closed_without_prepare` → `MIC_NOT_PREPARED`, poll None, stop Ok | PASS | OBSERVED |
| libav ffprobe (inherited) | `probe_capabilities` reports `LIBAV_UNAVAILABLE` (shared 62/62/60 DLLs not colocated) | NOT_VERIFIED (inherited, not Phase-6 scope) | NOT_VERIFIED |
| soak 30-min | Phase-4 gate | NOT_VERIFIED | NOT_VERIFIED |

New Phase-6 tests listed in §4 all PASS and counted in 41/144.

## 8. Evidence and completion

Files in `artifacts/ban_ke_hoach_v1/recording_engine_v2_phase_06/`:

- `EVIDENCE.md` — scoped SHA/diff, gap/fix table, 41 audio + 144 total test receipts, hardware probe (1 input/1 render), NOT_VERIFIED gates, raw logs
- `PHASE_06_REPORT.md` — this report
- `phase_06_verdict.json` — machine-readable verdict (PASS for Phase-6 mic contract, inherited libav + soak + permission chaos NOT_VERIFIED)

Implementation-ready completion requires event-driven WASAPI lifecycle correct, format negotiation fail-closed, 48k conversion with framing within 1 frame, mono preservation, mute data semantics, discontinuity/silence/device-loss handling, deterministic cleanup, fail-closed errors, focused deterministic tests, `cargo check`, no duplicate authority, truthful non-fabricated hardware evidence: **SATISFIED**. Formal engine `engine_available=true` additionally requires `libav_runtime_found` (shared DLLs) + soak, which remain NOT_VERIFIED and correctly remain out of Phase-6 verdict.

## 9. Mandatory worker self-review

1. **Full requirements?** §10 inspected before editing; event-driven path verified already correct with no busy polling; 48k + mono + mute honored; 8 deterministic tests added covering §10 bullets; `cargo check` + 144/5 tests PASS; real mic probe noninteractively exercised and recorded.
2. **Partial requirements?** Permission deny + device-loss chaos injection + long soak NOT_VERIFIED (packet says keep BLOCKED/NOT_VERIFIED) — explicit, not claimed.
3. **Architecture assumptions?** Shared-mode 100ms buffer (wasapi.rs HNS_BUFFER_100MS), queue 128, heartbeat 100ms, drift threshold 25ppm, default device roles eMultimedia→eCommunications — all documented in source.
4. **Duplicate authority?** None. `WasapiMicrophone` remains sole mic authority, `device.rs` sole endpoint opener, `loopback.rs` untouched.
5. **Crash/restart paths?** Worker stop flag + Stop + join + CloseHandle; prepare drops prior stream; Device invalidated → `is_available=false` + `last_error` (pipeline polls) — leak-free.
6. **Concurrency paths?** `StreamHandle: Send` (agile COM + HANDLE + atomics), `WorkerArgs: Send`, MTA per thread, no cross-thread libav touch, `AacEncoderPort: Send`.
7. **Previous-phase tests?** Phase-3 WGC (15+ tests), Phase-4 NVENC (19), Phase-5 muxer (36) still pass in full 144 run; Phase-5 libav ffprobe still NOT_VERIFIED (inherited, not Phase-6).
8. **Required tests not run?** All required unit/cargo check/audio filtered/hardware probe run and reported; NVENC 5 ignored are hardware diagnostics per packet (reported separately), not counted.
9. **Risks?** Thermal/soak/disk-full/NVENC init failure not in Phase-6 chaos matrix; documented as NOT_VERIFIED.
10. **Whether PASS is justified?** **Yes — PASS for Phase-6 isolated contract** (mic capture path implementation-ready, deterministic tests, real device exercised without fabrication, no authority violated, cargo check). Engine-level `PASS` (engine_available) correctly remains blocked by inherited libav DLLs/soak/permission, but those are out of Phase-6 scope and marked NOT_VERIFIED per packet.
