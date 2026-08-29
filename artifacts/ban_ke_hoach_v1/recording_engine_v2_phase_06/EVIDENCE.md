# Phase 6 — WASAPI Microphone — Evidence

**Baseline:** `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` (branch `refactor/architecture-v3-hardening`)
**Evidence generated:** 2026-08-28T23:55:00+07:00 (Phase 6 — WASAPI Microphone)
**Scope:** `apps/desktop/native/recording-engine/src/audio/**` — WasapiMicrophone, device WASAPI core, AAC resample/PTS/mute
**Commit state:** dirty working tree, no new commit (per packet: do not commit)

## 1. Baseline / Final SHA and scoped dirty status

| Item | Value | Classification |
|------|-------|----------------|
| Baseline SHA | `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` | OBSERVED |
| Final SHA (HEAD) | `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` (dirty) | OBSERVED |
| Phase-6 changed files (audio scope) | `src/audio/aac.rs` — 3 focused deterministic Phase-6 tests (channel preservation, 48k framing, mute semantics) <br> `src/audio/mod.rs` — 5 deterministic tests (PcmBlock framing, mock mute data semantics, state/idempotency, fail-closed defaults, TrackKind mapping) | OBSERVED |
| Pre-existing dirty (outside Phase-6 scope, preserved) | `src/capture/wgc.rs` (Phase-3), `src/encoder/mod.rs` + `nvenc_session.rs` (Phase-4), `src/muxer/libav.rs` (Phase-5 repair), ~20 execution/core/storage dirty files | OBSERVED |
| Git diff stat (audio) | `src/audio/aac.rs | 77 insertions(+)` <br> `src/audio/mod.rs | 75 insertions(+)` | OBSERVED |

```
git diff --stat HEAD -- apps/desktop/native/recording-engine/src/audio
 src/audio/aac.rs | 77 ++++++++++++++++++++++
 src/audio/mod.rs | 75 +++++++++++++++++++++
 2 files changed, 152 insertions(+)
```

## 2. Implementation gaps inspected and fixed

| Required §10 | Finding | Action | Classification |
|--------------|---------|--------|----------------|
| Inspect audio device/microphone/resampler/AAC code | `audio/mod.rs` (AudioCapturePort, PcmBlock, EncodedAudioPacket, MockAudioCapture), `audio/microphone.rs` (WasapiMicrophone thin wrapper over `device::wasapi::StreamHandle`, prepare→start→poll→stop→mute→is_available), `audio/device.rs` (1016 LOC — IMMDeviceEnumerator, endpoint selection, IAudioClient SHARED+EVENTCALLBACK, IAudioCaptureClient, WaitForSingleObject 100ms heartbeat, GetNextPacketSize/GetBuffer/ReleaseBuffer, format parsing, silent/device-loss/overflow/ComGuard lifecycle), `audio/aac.rs` (1148 LOC — clamp·scale s16, linear 48k resample, drift compensation, PtsBook anchor ring, MfAacEncoder), `audio/loopback.rs` (separate Phase-7 authority, not touched) reviewed before editing. | None — preserved authorities verified correct | STATICALLY_VERIFIED |
| Endpoint selection / event-driven IAudioClient / IAudioCaptureClient lifecycle | `device::wasapi::open` resolves empty id → default (eMultimedia then eCommunications), otherwise exact ACTIVE id match, never substituted; `CoInitializeEx(MTA)` via ComGuard, `CreateEventW` + `SetEventHandle`, `AUDCLNT_SHAREMODE_SHARED|EVENTCALLBACK` (+LOOPBACK for Phase-7 only), 100ms buffer, dedicated worker thread with WaitForSingleObject heartbeat, drain_packets loops GetNextPacketSize until 0, GetBuffer→convert→ReleaseBuffer exactly once. | Verified already-correct; no duplicate device/loop introduced | STATICALLY_VERIFIED |
| Format negotiation | `probe_from_tags` + `parse_mix_format` handles WAVE_FORMAT_PCM (16/32), IEEE_FLOAT (32), EXTENSIBLE (subformat GUID) with cbSize guard; unknown tag/bits→ `WASAPI_MIX_FORMAT_UNSUPPORTED` fail-closed; channels==0 or rate==0 rejected. | Verified correct | STATICALLY_VERIFIED |
| 48k conversion | `aac::linear_resample` ceil-scaled interleaved per-channel linear interpolation; identity when in==out; `MfAacEncoder::encode_block` resamples any input rate →48k before s16, then drift-compensated `linear_resample_scaled` when |ppm|≥25. Output locked to `AAC_OUTPUT_SAMPLE_RATE=48000`, `AAC_FRAME_FRAMES=1024`. Mono stays mono (channels preserved). | Verified correct + new deterministic framing tests added | STATICALLY_VERIFIED + OBSERVED |
| Discontinuity / silence / device-loss handling | `pcm_packet_to_f32` silent-flag → exact-length zeros preserving PTS; non-silent → interleaved f32; truncated → `WASAPI_PACKET_TRUNCATED` Fatal. `fault_from_error` classifies `AUDCLNT_E_DEVICE_INVALIDATED`/`RESOURCES_INVALIDATED` → Invalidated (marks unavailable, records last_error, worker exits); Transient → bounded retry (100) then `FAULT_LIMIT`; Fatal (truncated/undecodable) stops fail-closed. Overflow: 128-block VecDeque drops oldest, counts `overflow_dropped` for telemetry. QPC timestamps from `clock::qpc_now` (single authority §12). | Verified correct | STATICALLY_VERIFIED |
| Deterministic cleanup | `StreamHandle::stop` cooperative (stop flag → Stop → join within heartbeat), idempotent like mock; `Drop` does stop+join+CloseHandle even if never started; `WasapiMicrophone::prepare` drops previous stream first (joins worker) before opening new. | Verified correct | STATICALLY_VERIFIED |
| Fail-closed errors | Every failure surfaces as UPPER_SNAKE string: `WASAPI_COM_INIT_FAILED`, `WASAPI_ENUMERATOR_FAILED`, `WASAPI_DEVICE_NOT_FOUND`, `WASAPI_DEFAULT_DEVICE_NOT_FOUND`, `WASAPI_MIX_FORMAT_FAILED/UNSUPPORTED`, `WASAPI_INITIALIZE_FAILED`, `WASAPI_EVENT_CREATE_FAILED`, `WASAPI_SET_EVENT_FAILED`, `WASAPI_CAPTURE_SERVICE_FAILED`, `WASAPI_START_FAILED`, `WASAPI_ALREADY_STARTED`, `MIC_NOT_PREPARED`, `WASAPI_UNSUPPORTED_OS`, `AAC_UNSUPPORTED_CHANNEL_COUNT`, `AAC_BITRATE_OUT_OF_RANGE`, `MF_UNSUPPORTED_OS`, `AUDIO_DEVICE_INVALIDATED:0x88890004`. Unknown ids never substitute default. | Verified correct | STATICALLY_VERIFIED |
| Focused deterministic tests | Previously 8 deterministic aac helpers + 7 wasapi pure + 4 lifecycle (hardware-gated). Added 8 new hardware-free tests covering §10 bullets. | **ADDED:** `phase6_mono_stays_mono_no_fake_stereo`, `phase6_output_is_locked_to_48k_resampling_framing_within_one_frame`, `phase6_mute_data_semantics_preserves_frames_and_pts`, `pcmblock_frames_respects_channel_count`, `mock_mute_affects_captured_data_not_only_telemetry`, `mock_state_and_idempotency_before_and_after_prepare`, `wasapi_device_info_defaults_are_fail_closed`, `track_kind_maps_to_muxer_tracks` | OBSERVED |

No changes to `muxer/*` (Phase-5), `encoder/*` (Phase-4), `capture/*` (Phase-3), `service.rs` hard cutover, `loopback.rs` (Phase-7), `preview/*`, Tauri, frontend, or previous Phase artifacts — per packet authority.

## 3. Tests and gates — exact commands and results

### Cargo check

```
cargo check --manifest-path apps\desktop\native\recording-engine\Cargo.toml
```

Result: **PASS** — `Finished dev profile in 0.53s`, 0 errors, 19 pre-existing warnings only (unused NvEncGuid in nvenc_session diagnostics). **OBSERVED.**

### UNIT — audio (filtered)

```
cargo test --manifest-path apps\desktop\native\recording-engine\Cargo.toml --lib audio -- --test-threads=1 --nocapture
```

Result: **41 passed, 0 failed, 0 ignored** (OBSERVED)

- `s16_conversion_clamps_symmetrically` — PASS
- `byte_pack_is_little_endian_interleaved` — PASS
- `resample_identity_preserves_length_and_content` — PASS
- `resample_44100_to_48000_scales_length_within_one_frame` — PASS
- `resample_keeps_channel_interleaving` — PASS
- `compensated_frame_count_squeezes_fast_and_stretches_slow_devices` — PASS
- `scaled_resampler_is_exact_identity_at_scale_one` — PASS
- `scaled_resampler_matches_drift_ratio_within_one_frame_per_second` — PASS
- `pts_progression_crosses_1024_frame_boundaries_monotonically` — PASS
- `pts_stays_strictly_monotonic_when_emission_lags_a_full_block` — PASS
- `loopback_silence_gap_restarts_timeline_at_resuming_anchor` — PASS
- `anchor_ring_prunes_unreachable_entries` — PASS
- `pre_stream_offsets_fall_back_to_first_anchor` — PASS
- `asc_matches_muxer_contract_for_allowed_channel_counts` — PASS
- `new_validates_purely_before_touching_the_os` — PASS
- `present_degrades_gracefully` — PASS
- `real_encode_round_trip_when_mft_present` — **PASS** (6 × 4800 mono frames → 26 AAC packets, PTS strictly monotonic, drain continues line)
- `phase6_mono_stays_mono_no_fake_stereo` — **PASS** (new, mono 1024 → s16 2048 bytes not 4096, resample 44100→48000 length within 1, ASC mono+stereo ok, ch 6 rejected)
- `phase6_output_is_locked_to_48k_resampling_framing_within_one_frame` — **PASS** (new, 44.1k/48k/32k/96k mono+stereo framing within 1 frame, AAC_OUTPUT 48k)
- `phase6_mute_data_semantics_preserves_frames_and_pts` — **PASS** (new, silent flag zeros exact length, s16 zeros)
- `extensible_float_is_recognized` — PASS
- `plain_pcm16_and_float_tags_are_recognized` — PASS
- `unsupported_formats_fail_closed` — PASS
- `f32_packets_round_trip_little_endian` — PASS
- `i16_packets_scale_into_unit_range` — PASS
- `silent_flag_zeroes_but_preserves_frame_count` — PASS
- `truncated_packets_are_rejected` — PASS
- `probes_degrade_gracefully_without_hardware` — PASS
- `lifecycle_fails_closed_without_prepare` (loopback) — PASS
- `unknown_device_id_is_rejected_not_substituted` (loopback) — PASS
- `default_render_round_trip_when_present` — PASS (if hardware)
- `lifecycle_fails_closed_without_prepare` (mic) — PASS
- `unknown_device_id_is_rejected_not_substituted` (mic) — PASS
- `default_device_round_trip_when_present` (mic) — PASS
- `re_prepare_replaces_stream_cleanly` (mic) — PASS
- `pcmblock_frames_respects_channel_count` — **PASS** (new, 960 stereo, 480 mono, 0 empty)
- `mock_mute_affects_captured_data_not_only_telemetry` — **PASS** (new, unmuted carries signal, muted delivers exact-length zeros preserving channels)
- `mock_state_and_idempotency_before_and_after_prepare` — **PASS** (new, poll before start None, prepare→is_available, start/stop idempotent, mute toggles)
- `wasapi_device_info_defaults_are_fail_closed` — **PASS** (new)
- `track_kind_maps_to_muxer_tracks` — **PASS** (new)
- `collect_audio_asc_covers_every_aac_track_and_fails_closed` (service) — PASS

### FULL — all recording-engine lib tests

```
cargo test --manifest-path apps\desktop\native\recording-engine\Cargo.toml --lib -- --test-threads=1
```

Result: **144 passed, 0 failed, 5 ignored** (OBSERVED) — 5 ignored = NVENC hardware probes (`preset_config_combo_matrix`, `initialize_params_matrix`, `session_lifecycle_probe`, `production_encode_texture_probe`, `production_shape_sustained_probe`) — manual driver diagnostics, not counted. Prior baseline 136 passed; +8 Phase-6 audio tests = 144.

### HARDWARE — microphone probe (non-interactive, OBSERVED, no simulation)

```
cargo run --bin probe_temp  (temporary, then removed)
# uses probe::probe_capabilities(None) + device::wasapi_available/list_*_endpoints

wasapi_available=true
mic_available=true
system_available=true
aac_available=true
blockers=["LIBAV_UNAVAILABLE: ... (shared avformat-62/avcodec-62/avutil-60 DLLs not colocated)"]
wasapi_fn=true
default_input=true
default_render=true
input_endpoints=1 ["{0.0.1.00000000}.{787cf9c8-4511-40fb-b284-9e416b51440b}"]
render_endpoints=1 ["{0.0.0.00000000}.{c8f7294e-ac9a-43d9-9ddb-89d2afaa6e63}"]
```

- `WasapiMicrophone::default_device_round_trip_when_present` — **PASS** (prepared default, negotiated channels≥1 rate>0, device_id non-empty, mute toggle pre-start idempotent, start→120ms capture→mute→60ms→stop→drain well-formed, overflow 0)
- `WasapiMicrophone::unknown_device_id_is_rejected_not_substituted` — **PASS** (`WASAPI_DEVICE_NOT_FOUND`)
- `WasapiMicrophone::lifecycle_fails_closed_without_prepare` — **PASS** (`MIC_NOT_PREPARED`, poll None, stop idempotent)
- `WasapiMicrophone::re_prepare_replaces_stream_cleanly` — **PASS**
- `audio::aac::tests::real_encode_round_trip_when_mft_present` — **PASS** (MFT present, mono 1ch → 48k AAC 26 packets, PTS monotonic)

Environment: Windows 11, same host as probe above. No hardware evidence fabricated — endpoints enumerated via IMMDeviceEnumerator, failures would be typed strings.

## 4. Evidence tables — classification per claim

| Claim | Verification | Classification |
|-------|--------------|----------------|
| `AudioCapturePort` + `EncodedAudioPacket` contracts preserved (single clock/audio packet) | `audio/mod.rs` trait unchanged; `WasapiMicrophone` sole production mic authority, `device::wasapi::StreamHandle` sole capture loop | STATICALLY_VERIFIED |
| `WasapiMicrophone` reuses `audio/device.rs` endpoint opening, never second device/loop | `microphone.rs::prepare` calls `device::open_microphone_stream`; `device.rs` is shared core with `loopback.rs` but separate StreamHandle per track (never mixed) | STATICALLY_VERIFIED |
| No muxer/encoder/capture/service hard cutover/loopback(Phase-7)/preview/Tauri/frontend changes | `git diff --stat HEAD -- apps/desktop/native/recording-engine/src/audio` shows only `audio/aac.rs` + `audio/mod.rs`; `git diff --stat HEAD -- src/muxer src/encoder src/capture src/service.rs` shows preserved dirty only | OBSERVED |
| Mic stays native channel count (mono stays mono) then resamples to 48k, no fake stereo | `device::FormatProbe` preserves channels from mix format; `aac::linear_resample` per-channel; `MfAacEncoder::new` rejects 0 or >2; new test `phase6_mono_stays_mono_no_fake_stereo` asserts mono s16 2048 bytes (not 4096) and ASC mono+stereo | STATICALLY_VERIFIED + OBSERVED |
| Mic mute affects captured/encoded recorder data, not merely telemetry/UI | `device::wasapi::SharedState::muted` zeroed in `drain_packets` (PTS continuity); `MockAudioCapture::set_muted` zeroes samples; new tests `phase6_mute_data_semantics...` + `mock_mute_affects_captured_data_not_only_telemetry` assert exact-length zeros preserving channels | STATICALLY_VERIFIED + OBSERVED |
| Endpoint selection | Empty → default (eMultimedia→eCommunications), exact ACTIVE id match else `WASAPI_DEVICE_NOT_FOUND`, never substituted | STATICALLY_VERIFIED + OBSERVED (unknown_device tests) |
| Event-driven IAudioClient/IAudioCaptureClient lifecycle | SHARED+EVENTCALLBACK, CreateEvent+SetEventHandle, WaitForSingleObject 100ms heartbeat, GetNextPacketSize→GetBuffer→ReleaseBuffer with ComGuard MTA | STATICALLY_VERIFIED |
| Format negotiation | WAVE_FORMAT_PCM/IEEE_FLOAT/EXTENSIBLE, cbSize guard, unsupported→fail-closed | STATICALLY_VERIFIED + OBSERVED (wasapi pure tests) |
| 48k conversion + framing | Linear resample ceil-scaled, framing within 1 output frame for 44.1k/32k/96k/48k; drift compensation ±25ppm threshold | STATICALLY_VERIFIED + OBSERVED (new framing test) |
| Discontinuity/silence/device-loss handling | Silent flag→zeros, truncated→Fatal, INVALIDATED→mark unavailable + last_error, transient bounded 100, overflow drops oldest with counter | STATICALLY_VERIFIED + OBSERVED (silent/truncated/device tests) |
| Deterministic cleanup + fail-closed errors | Drop joins worker, stop idempotent, prepare drops prior stream; every failure UPPER_SNAKE | STATICALLY_VERIFIED + OBSERVED (lifecycle + re_prepare tests) |
| Deterministic tests added (channel, 48k framing, mute, state/idempotency/error) | 8 new hardware-free tests listed above, all PASS | OBSERVED |
| Real microphone probe (noninteractive, actual device) | `wasapi_available=true`, 1 input + 1 render endpoint, `default_device_round_trip_when_present` exercised real start/stop/drain; no fabrication | OBSERVED |
| Microphone permission (user deny) gate | Not triggered on this host; Windows privacy prompt not denied → permission path not exercised | NOT_VERIFIED (remains BLOCKED/NOT_VERIFIED per packet) |
| Long soak A/V drift / device-loss chaos injection | Not run per packet (no 30-min soak, no chaos matrix in this phase) | NOT_VERIFIED |
| Real libav MKV ffprobe (Phase-5 gate) | Still unavailable — shared DLLs not colocated (`LIBAV_UNAVAILABLE`); not Phase-6 scope but inherited | NOT_VERIFIED |

## 5. Changed files (Phase 6 scope only)

- `apps/desktop/native/recording-engine/src/audio/aac.rs` — added 3 deterministic Phase-6 tests (§10 channel/48k/mute) after existing `encoder_fails_closed_off_windows`; no production code changed.
- `apps/desktop/native/recording-engine/src/audio/mod.rs` — added `#[cfg(test)] mod phase6_tests` with 5 tests (PcmBlock framing, mock mute data, idempotency, defaults, TrackKind mapping); no production trait change.

Artifacts created in this pass:

- `artifacts/ban_ke_hoach_v1/recording_engine_v2_phase_06/EVIDENCE.md` (this file)
- `artifacts/ban_ke_hoach_v1/recording_engine_v2_phase_06/PHASE_06_REPORT.md`
- `artifacts/ban_ke_hoach_v1/recording_engine_v2_phase_06/phase_06_verdict.json`

## 6. Raw logs (selected)

```
cargo check → Finished dev profile in 0.53s, 0 errors, 19 pre-existing warnings
cargo test audio --lib --test-threads=1 --nocapture → 41 passed, 0 failed
  real_encode_round_trip_when_mft_present PTS sequence (26): [0, 21333, ... 533333] packet byte sizes: [376, ... 246] — mono PTS strictly monotonic
cargo test --lib --test-threads=1 → 144 passed, 0 failed, 5 ignored
  5 ignored = NVENC hardware probes (not counted)
cargo run --bin probe_temp → wasapi_available=true mic_available=true system_available=true aac_available=true
  input_endpoints=1 {0.0.1.00000000}.{787cf9c8-...} render_endpoints=1 {0.0.0.00000000}.{c8f7294e-...}
  blockers=[LIBAV_UNAVAILABLE ...]
audio::microphone::tests::default_device_round_trip_when_present → ok (no skip — hardware exercised)
audio::microphone::tests::unknown_device_id_is_rejected_not_substituted → ok (WASAPI_DEVICE_NOT_FOUND)
git diff --stat HEAD -- audio → 2 files changed, 152 insertions(+)
```

## 7. Limitations and remaining gates

- **Microphone permission deny path** — not triggered; Windows Settings → Privacy → Microphone was not denied during this run. The worker's `AUDCLNT_E_DEVICE_INVALIDATED` path is fail-closed and tested via fault classification, but a live permission-revocation chaos test (disable mic mid-take) was not executed per packet scope. Classified NOT_VERIFIED.
- **Device-loss chaos** — USB unplug / default device switch mid-take not injected in this phase; `last_error` + `is_available=false` contract is code-reviewed and unit-tested (fault mapping, `unknown_device` rejection) but not live-injected. NOT_VERIFIED per plan.
- **Inherited Phase-5 libav ffprobe** — `LibavRuntime::load()` still reports `LIBAV_UNAVAILABLE` (no shared 62/62/60 DLLs colocated; only static ffmpeg/ffprobe 8.1.2 on PATH). Real segmented MKV ffprobe remains NOT_VERIFIED; does not block Phase-6 mic contract but is noted.
- **Long soak drift compensation** — §12 drift measured via `compensated_frame_count` + `PtsBook` unit tests; a multi-minute live soak comparing mic wall-clock vs QPC not run. NOT_VERIFIED (Phase-8/19 gate).

## 8. Verdict (advisory, within this evidence file)

`PASS` for Phase 6 WASAPI Microphone contract (event-driven capture, format negotiation, 48k resample with framing within 1 frame, mono preservation, mute data semantics, discontinuity/silence/device-loss fail-closed, deterministic cleanup, 41 audio + 144 total tests PASS, real default mic exercised without fabrication, no authority violated). Hardware permission/device-loss chaos gates remain NOT_VERIFIED as packet requires; inherited libav gate remains NOT_VERIFIED but out of scope for Phase 6.
