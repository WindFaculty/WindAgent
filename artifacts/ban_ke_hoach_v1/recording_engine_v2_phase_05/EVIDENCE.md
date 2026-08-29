# Phase 5 — Native MKV / libavformat — Evidence (Repair 1)

**Baseline:** `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` (branch `refactor/architecture-v3-hardening`)
**Evidence generated:** 2026-08-28T23:45:00+07:00 (Phase 5 Repair 1 — preserve B-frame PTS/DTS)
**Scope:** `apps/desktop/native/recording-engine/src/muxer/**` — LibavMuxer native path, libav_loader, tracks, timestamps, mock
**Commit state:** dirty working tree, no new commit (per packet: do not commit)

## 1. Baseline / Final SHA and scoped dirty status

| Item | Value | Classification |
|------|-------|----------------|
| Baseline SHA | `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` | OBSERVED |
| Final SHA (HEAD) | `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` (dirty) | OBSERVED |
| Phase-5 changed files (muxer scope) | `src/muxer/libav.rs` — SegmentState per-slot DTS+PTS tracking, B-frame-aware `validate_packet_contract`, write_native DTS monotonic preservation, misleading B-frame comment removed, 10 focused contract tests (Repair 1 replaces blanket DTS==PTS reject) | OBSERVED |
| Pre-existing dirty (outside Phase-5 scope, preserved) | `src/capture/wgc.rs` (Phase-3 invalid-source), `src/encoder/mod.rs` + `nvenc_session.rs` (Phase-4 PTS-zero repair), ~20 execution/core/storage dirty files | OBSERVED |
| Git diff stat (muxer) | `src/muxer/libav.rs  | 345 insertions(+), 7 deletions(-)` | OBSERVED |

```
git diff --stat HEAD -- apps/desktop/native/recording-engine/src/muxer
  src/muxer/libav.rs | 345 ++++++++++++++++++++-
  1 file changed, 338 insertions(+), 7 deletions(-)
```

## 2. Implementation gaps inspected and fixed

| Required 1-7 | Finding | Action | Classification |
|--------------|---------|--------|----------------|
| 1. Inspect API/muxer/tracks/service before editing | `muxer/libav.rs` (1240+ LOC), `libav_loader.rs` (968 LOC), `tracks.rs` (297), `timestamps.rs` (158), `mod.rs` (91), `mock.rs` (181), `service.rs` build_native_ports, `encoder/nvenc_session.rs` has_b_frames DTS logic (`pts - output_duration`), `encoder/mod.rs` VideoConfig.b_frames exposed (0..4). Lifecycle, FFI transcriptions (60/62/62), avcC/hvcC/AAC builders verified correct. | None — preserved | STATICALLY_VERIFIED |
| 2. Native runtime lifecycle | `open_native`: `alloc_output_context("matroska")`, `guess_format` check, per-track `new_stream` + `AVCodecParameters` (codec_type/id/tag/width/height/format/sar/framerate/sample_rate/channel_layout), `time_base=1/TIMEBASE_DEN`, avg_frame_rate, `packet_alloc`, `avio_open(.tmp)`. `flush_header`: stage avcC/hvcC/ASC via `av_mallocz` then `avformat_write_header`. `write_native`: `av_new_packet` → copy → pts/dts/duration/pos/flags/stream_index → `av_packet_rescale_ts` (PTS and DTS rescaled together) → `av_interleaved_write_frame` → `av_packet_unref`. `close_native`: header_written guard, `av_write_trailer` → `avio_closep` → `packet_free`/`free_context` → `OpenOptions::write(true).open(.tmp)` → `sync_all` → `rename .tmp→.mkv` → stat. All returns error-checked, negative codes via `err_str`. | Verified already-correct; no structural change needed beyond timestamp validation | STATICALLY_VERIFIED |
| 3. Fail-closed state behavior — GAP FOUND (Repair 1) | Initial Phase-5 fix added `validate_packet_contract` but rejected every `dts_us != pts_us` as `MKV_BFRAMES_UNSUPPORTED`. This silently removed supported `VideoConfig.b_frames` profile feature; `NvencSession` has explicit `has_b_frames` DTS logic (`dts = pts - output_duration`, DTS<=PTS). Also `write_native` previously used only PTS monotonic; DTS monotonic (written-order) never tracked. Misleading comment claimed V2 disables B-frames. | **FIXED (Repair 1):** Replaced blanket `DTS==PTS` reject with B-frame-capable validation: DTS monotonic in written (decode) order per slot (`last_dts_by_slot`), zero PTS/DTS valid, `0 <= DTS <= PTS` enforced, PTS preserved verbatim via AVPacket (both fields rescaled together). Added `SegmentState::last_dts_by_slot: Vec<Option<i64>>` (init in open_native) alongside `last_pts_by_slot`. Removed `MKV_BFRAMES_UNSUPPORTED` and V2-disables-B-frames comment. `write_native` now stores both per-slot DTS and PTS exactly (no max). | OBSERVED (source diff) + STATICALLY_VERIFIED |
| 4. Monotonic / zero-PTS / B-frames — REPAIRED | Phase-4 guarantees PTS zero valid and monotonic when B-frames disabled (repaired 2026-08-29). NvencSession produces DTS<=PTS with DTS monotonic in decode order when `b_frames>0`. Muxer must preserve both. Previous muxer rejected all DTS!=PTS and enforced PTS monotonic in written order, which rejects valid reordered B-frame sequences (e.g., decode I0/P3/B1 has written-order PTS 0,100k,33k non-monotonic but DTS monotonic 0,33k,50k valid). | **FIXED:** Added `last_dts_by_slot` for written-order DTS monotonic; `validate_packet_contract` now checks: track exists, data non-empty, codec matches, `this_pts>=0`, `this_dts>=0`, `this_dts<=this_pts`, `this_dts >= prev_dts` per slot else `TIMESTAMP_REGRESSION`. PTS monotonic in presentation order is not enforced in written order when DTS!=PTS — muxer preserves PTS verbatim and relies on DTS monotonic + `av_packet_rescale_ts` on both fields. Zero preserved (`==` allowed, `<` is regression for DTS). Documented written-order (decode) vs presentation-order distinction in code comments and evidence. | STATICALLY_VERIFIED + OBSERVED (new B-frame tests) |
| 5. Real MKV via ffprobe | Host has static `ffprobe 8.1.2-full_build-www.gyan.dev` and `ffmpeg 8.1.2` (PATH `C:\...\ffmpeg-8.1.2-full_build\bin\ffprobe.exe`). No shared `avformat-62.dll/avcodec-62.dll/avutil-60.dll` installed. `LibavRuntime::load()` probes `WINDAGENT_LIBAV_DIR` (not set) → exe dir → PATH across families 62/61/60 and reports every `LoadLibraryW` failure. `muxer::libav::tests::keyframe_flag_reaches_mkv_simpleblock` therefore `eprintln!("skipping: libav runtime unavailable")` and returns without producing a real `.mkv`; probe not claimed. Previously mock `.tmp` ffprobe on non-Matroska bytes was incorrectly considered; now correctly classified. | **No simulation:** recorded as NOT_VERIFIED with exact blocker string; ffprobe not run on a Libav-produced file because none could be created without shared DLLs. Mock segment ffprobe correctly fails as expected (non-Matroska) and is marked OBSERVED negative control, not PASS. | NOT_VERIFIED (real Libav MKV) — blocker truthfully reported |
| 6. Focused tests | Existing muxer tests: 27 + 7 from first pass = 34. Repair 1 adds/replaces B-frame tests: valid zero, valid B-frame DTS!=PTS accepted, reordered PTS accepted when DTS monotonic, DTS regression rejected, DTS>PTS / negative DTS rejected, codec mismatch, empty, unknown track, tmp-not-promoted. Full suite single-threaded now 136 passed. | **ADDED/REPLACED:** `valid_bframe_dts_pts_accepted`, `bframe_reordered_pts_accepted_when_dts_monotonic`, `rejects_dts_regression_and_invalid_timestamps` plus preserved `timestamp_zero...`, `rejects_timestamp_regression...`, `rejects_codec_mismatch...`, `rejects_empty...`, `rejects_unknown_track`, `segmentation_tmp_never_promoted_on_failure` = 10 contract tests total. `rejects_bframes_explicitly_v2_contract` removed (was misleading). | OBSERVED |
| 7. Cargo check / build | `cargo check` passes 0 errors, warnings pre-existing only. | Verified | OBSERVED |

## 3. Tests and gates — exact commands and results

### Cargo check

```
cargo check --manifest-path apps\desktop\native\recording-engine\Cargo.toml
```

Result: **PASS** — `Finished dev profile in 0.64s`, 0 errors, warnings pre-existing only. **OBSERVED.**

### UNIT — muxer (filtered)

```
cargo test --manifest-path apps\desktop\native\recording-engine\Cargo.toml muxer --lib -- --test-threads=1
```

Result: **36 passed, 0 failed, 0 ignored** (OBSERVED)

- `channel_masks_cover_mono_and_stereo_only` — PASS
- `delivery_token_uses_take_folder_never_raw_paths` — PASS
- `finalize_rejects_open_segment_and_resets_when_clean` — PASS
- `index_sequence_is_monotonic_fail_closed` — PASS
- `layout_validation_rejects_bad_orders_duplicates_and_rates` — PASS
- `bframe_reordered_pts_accepted_when_dts_monotonic` — **PASS** (new, B-frame reordered PTS 60k→30k accepted when DTS 20k→30k monotonic)
- `valid_bframe_dts_pts_accepted` — **PASS** (new, DTS 16k != PTS 33k accepted)
- `rejects_codec_mismatch_per_track` — PASS (preserved)
- `rejects_dts_regression_and_invalid_timestamps` — **PASS** (new, DTS 40k<50k rejected, DTS>PTS rejected, negative DTS rejected)
- `rejects_empty_packet_data` — PASS
- `rejects_timestamp_regression_per_track` — **PASS** (preserved, now DTS-based)
- `rejects_unknown_track` — PASS
- `router_roll_sequence_drives_increasing_segment_indexes` — PASS
- `segment_paths_are_stable_and_tmp_suffixed` — PASS
- `segmentation_tmp_never_promoted_on_failure` — PASS (empty-segment close leaves no .mkv)
- `state_machine_fails_closed_without_runtime` — PASS
- `timestamp_zero_is_valid_and_monotonic_per_track` — PASS (zero valid, per-track DTS+PTS)
- `loader_is_total_and_never_panics` — PASS
- `nul_terminated_rejects_embedded_nul` — PASS
- `transcribed_layouts_match_the_headers` — PASS
- `verified_constants_match_ffmpeg_n8_1_2` — PASS
- `version_major_decodes_ffmpeg_packed_int` — PASS
- `segments_are_fsynced_renamed_and_report_bytes` (mock) — PASS
- `packets_before_boundary_stay_current` — PASS
- `idr_at_boundary_opens_next_segment` — PASS
- `non_keyframe_past_boundary_is_held_not_routed` — PASS
- `monotonic_guard_rejects_regressions` — PASS
- `aac_asc_encodes_lc_48k_stereo` — PASS
- `avcc_layout_matches_iso_14496_15` — PASS
- `avcc_needs_both_parameter_sets` — PASS
- `hvcc_layout_matches_iso_14496_15_hevc` — PASS
- `length_prefixed_matches_avcc_length_size_of_four` — PASS
- `length_prefixed_passes_non_annexb_data_through` — PASS
- `splits_three_and_four_byte_start_codes` — PASS
- `keyframe_flag_reaches_mkv_simpleblock` — **PASS (skipped runtime, not counted as real probe)** — host `LibavRuntime::load()` unavailable, prints `skipping: libav runtime unavailable` twice, test harness reports `ok` but classified NOT as real libav validation

### FULL — all recording-engine lib tests

```
cargo test --manifest-path apps\desktop\native\recording-engine\Cargo.toml --lib -- --test-threads=1
```

Result: **136 passed, 0 failed, 5 ignored** (OBSERVED) — 5 ignored = NVENC hardware probes (`preset_config_combo_matrix`, `initialize_params_matrix`, `session_lifecycle_probe`, `production_encode_texture_probe`, `production_shape_sustained_probe`) — manual driver diagnostics, not counted.

### HARDWARE / native loader probe — OBSERVED, no simulation

```
cargo test --manifest-path apps\desktop\native\recording-engine\Cargo.toml --lib muxer::libav_loader::tests::loader_is_total_and_never_panics -- --nocapture
→ ok
cargo test --manifest-path apps\desktop\native\recording-engine\Cargo.toml --lib muxer::libav::tests::keyframe_flag_reaches_mkv_simpleblock -- --nocapture
→ ok (with "skipping: libav runtime unavailable on this host" x2)
```

Environment: Windows 11, `where ffprobe` → `...\ffmpeg-8.1.2-full_build\bin\ffprobe.exe`, `ffprobe -version` → `8.1.2-full_build-www.gyan.dev` / `libavutil 60.26.102 / libavcodec 62.28.102 / libavformat 62.x`. Shared DLL probe result (from `LibavRuntime::load_uncached` source and observed test behavior):

```
LIBAV_UNAVAILABLE: probed 3 location(s) × 3 release family(ies), no usable avformat/avcodec/avutil.
Failures: LoadLibraryW(avutil-60.dll via PATH) → The specified module could not be found
  | LoadLibraryW(avcodec-62.dll ...) | LoadLibraryW(avformat-62.dll ...)
  + same for avutil-59/avcodec-61/avformat-61 and avutil-58/avcodec-60/avformat-60
  + WINDAGENT_LIBAV_DIR not set, exe dir probe also fails
```

Concrete probe output captured:

- `loader_is_total_and_never_panics` asserts `msg.starts_with("LIBAV_UNAVAILABLE")` — **PASS**
- `keyframe_flag_reaches_mkv_simpleblock` observes unavailable and returns — **not counted as probe PASS**

### ffprobe on mock segment — OBSERVED negative control

```
ffprobe -v error -show_format -show_streams <temp>\segment_0000.mkv
→ "Invalid data found when processing input" (mock starts with 0x1A45DFA3 + text lines, not Matroska)
```

Mock segment ffprobe correctly fails Matroska parsing — mock correctly not claimed as real MKV. **OBSERVED, NOT_VERIFIED as real validation.**

### ffprobe on Libav-produced segment — NOT_VERIFIED (blocker)

No `segment_*.mkv` produced by `LibavMuxer` exists on this host because `LibavRuntime::load()` fails before `alloc_output_context`. Therefore no command like `ffprobe -show_streams -show_entries stream=codec_name,avg_frame_rate,r_frame_rate,duration -print_format json segment_0000.mkv` could be executed successfully. **NOT_VERIFIED. Not simulated.** Prior mock `.tmp` ffprobe result is not valid evidence and is marked NOT_VERIFIED, not PASS.

## 4. Evidence tables — classification per claim

| Claim | Verification | Classification |
|-------|--------------|----------------|
| Output context / streams / codecpar / AVIO (.tmp) / packet / rescale (PTS+DTS together) / interleaved write / trailer / io_close / flush+fsync+rename lifecycle present and error-checked | Source inspection of `libav.rs::{open_native,flush_header,write_native,close_native}` + `libav_loader` wrappers each returns `Result` with `err_str` | STATICALLY_VERIFIED |
| Per-track DTS monotonic in written (decode) order, zero valid, DTS<=PTS, DTS>=0 not fabricated, per-track PTS preserved verbatim (presentation order not enforced in written order when B-frames reorder), empty/codec mismatch/unknown track fail-closed | `validate_packet_contract` with `last_dts_by_slot` + `last_pts_by_slot` + new B-frame tests: zero valid, B-frame DTS!=PTS accepted, reordered PTS accepted when DTS monotonic, DTS regression/invalid rejected | STATICALLY_VERIFIED + OBSERVED (10 contract tests PASS) |
| Written-order vs presentation-order distinction: DTS is decode order (what MKV interleaves), PTS is presentation order (what player displays). With B-frames, PTS in decode order is non-monotonic (e.g., decode I0/P3/B1 has PTS 0,100k,33k) — muxer preserves both fields via AVPacket pts/dts + `av_packet_rescale_ts` identity 1/1e6 → stream time_base; DTS monotonic ensures decode-order validity. | Code comments in SegmentState + validate_packet_contract + evidence section 7 | STATICALLY_VERIFIED + OBSERVED |
| `av_packet_rescale_ts` rescale 1/1_000_000 → stream time_base preserves QPC micros for both PTS and DTS; keyframe `AV_PKT_FLAG_KEY` set from `is_keyframe` | `write_native` sets `pts=pts_from_micros(pts_us)`, `dts=dts_us`, `flags= is_keyframe?0x0001:0`, `stream_index`, then `rescale_ts` on the same packet | STATICALLY_VERIFIED |
| Segmentation: `.tmp` → trailer → fsync (reopened WRITE handle) → atomic rename; no arbitrary split (caller forces IDR, router holds `HoldForNext` until IDR, `RollTo` opens next); each file independently playable only after header/trailer | `close_native` order, `SegmentRouter` `request_roll/boundary` + `LibavMuxer::assert_index_sequence` monotonic | STATICALLY_VERIFIED |
| B-frame handling: no `MKV_BFRAMES_UNSUPPORTED` blanket reject; valid B-frame DTS/PTS accepted, invalid DTS>PTS / negative / regression rejected; VideoConfig.b_frames (0..4) and NvencSession has_b_frames DTS logic preserved | Source diff shows `MKV_BFRAMES_UNSUPPORTED` removed, new validation, 3 new B-frame tests PASS | OBSERVED |
| Loader probes 3 locations × 3 families newest-first, dependency order avutil→avcodec→avformat, version readback, ABI gate 62/62/60 | `libav_loader::tests::transcribed_layouts_match_the_headers`, `verified_constants_match_ffmpeg_n8_1_2`, `version_major_decodes_ffmpeg_packed_int`, `loader_is_total_and_never_panics` PASS | OBSERVED |
| Real MKV `ffprobe` : valid Matroska container, H264/HEVC stream, FPS metadata 60, monotonic timestamps, no corrupt tail | **NOT_VERIFIED** — shared DLLs unavailable (static ffmpeg build only); `keyframe_flag_reaches_mkv_simpleblock` skipped with `libav runtime unavailable` | NOT_VERIFIED |
| 30-minute soak Phase 4 gate | NOT_VERIFIED per `UNRESOLVED_GATES.md` (does not block this phase) | NOT_VERIFIED |

## 5. Changed files (Phase 5 Repair 1 scope only)

- `apps/desktop/native/recording-engine/src/muxer/libav.rs` — added `SegmentState::last_dts_by_slot: Vec<Option<i64>>` (init `vec![None; tracks.len()]` in `open_native` and `synth_segment_state`), rewrote `validate_packet_contract` to B-frame-capable: checks `this_pts>=0`, `this_dts>=0`, `this_dts<=this_pts`, per-slot DTS monotonic `this_dts < prev_dts → TIMESTAMP_REGRESSION` (written-order), PTS preserved verbatim without written-order monotonic when DTS!=PTS, removed `MKV_BFRAMES_UNSUPPORTED`, updated `write_native` bookkeeping to store both DTS and PTS per slot + global `last_pts_us` exactly (no max), updated comments to explain written vs presentation distinction, replaced `rejects_bframes_explicitly_v2_contract` with `valid_bframe_dts_pts_accepted`, `bframe_reordered_pts_accepted_when_dts_monotonic`, `rejects_dts_regression_and_invalid_timestamps` (plus `rejects_timestamp_regression_per_track` preserved as DTS-based), added `mk_b_packet` helper and `last_dts_by_slot` to `synth_segment_state`. Total 338 insertions.

No changes to `capture/*`, `encoder/*` (Phase-4 repair preserved), `audio/*`, `preview/*`, `service.rs` hard cutover, Tauri, frontend, or unrelated artifacts.

Artifacts created in this pass:

- `artifacts/ban_ke_hoach_v1/recording_engine_v2_phase_05/EVIDENCE.md` (this file)
- `artifacts/ban_ke_hoach_v1/recording_engine_v2_phase_05/PHASE_05_REPORT.md`
- `artifacts/ban_ke_hoach_v1/recording_engine_v2_phase_05/phase_05_verdict.json`

## 6. Raw logs (selected)

```
cargo check → Finished dev profile in 0.64s, 0 errors
cargo test muxer --lib --test-threads=1 → 36 passed, 0 failed
cargo test --lib --test-threads=1 → 136 passed, 0 failed, 5 ignored
loader_is_total_and_never_panics → ok (LIBAV_UNAVAILABLE prefix)
keyframe_flag_reaches_mkv_simpleblock → ok (skipping: libav runtime unavailable x2)
ffprobe -version → 8.1.2-full_build-www.gyan.dev
ffprobe <mock>.mkv → Invalid data found when processing input (NOT_VERIFIED, not PASS)
git diff --stat HEAD -- muxer → src/muxer/libav.rs 338 insertions
```

## 7. Written-order vs presentation-order distinction

**Written (decode) order** is the order `LibavMuxer::write_packet` is called and `av_interleaved_write_frame` emits SimpleBlocks. This is NVENC's output order. When `b_frames>0`, `NvencSession::lock_packets` computes `dts_us = pts_us - output_duration` with `has_b_frames=true`, so DTS lags PTS (`DTS <= PTS`). The decode order's DTS must be nondecreasing per track; the muxer enforces `last_dts_by_slot` monotonic and rejects `TIMESTAMP_REGRESSION` on DTS.

**Presentation order** is the order a player displays frames, sorted by PTS. With B-frames, presentation-order PTS is monotonic (0,33k,66k,100k) but written-order PTS is not (e.g., decode I0/P3/B1 has PTS 0,100k,33k). The previous implementation enforced PTS monotonic in written order and rejected every `DTS != PTS` as `MKV_BFRAMES_UNSUPPORTED`, which incorrectly blocked the valid `VideoConfig.b_frames` (0..4) profile feature. Repair 1 preserves `EncodedPacket{pts_us,dts_us}` verbatim into `AVPacket{pts,dts}` then `av_packet_rescale_ts` on the same packet, and does not enforce PTS monotonic in written order when DTS != PTS. Only gross invalid `DTS>PTS` or negative timestamps are rejected. This matches `encoder::NvencConfig` and `NvencSession` B-frame semantics.

Global `last_pts_us = prev.max(pts)` masking is removed; only per-slot `last_dts_by_slot` (and `last_pts_by_slot` for bookkeeping) with exact store is used.

## 8. Limitations and remaining gates

- **Real Libav MKV ffprobe** (`valid container / H264/HEVC / 60 FPS / monotonic / no corrupt tail`) remains **NOT_VERIFIED** on this host because the engine's runtime loader requires shared `avformat-62.dll/avcodec-62.dll/avutil-60.dll` colocated via `WINDAGENT_LIBAV_DIR` or exe dir or PATH, but this host only has the static `ffmpeg.exe/ffprobe.exe` (no shared DLLs). Honest blocker reported, not simulated. Prior ffprobe on mock `.tmp` bytes is correctly classified **NOT_VERIFIED**, not PASS.
- **30-minute NVENC soak** (Phase 4 gate) remains NOT_VERIFIED per `UNRESOLVED_GATES.md` and does not block this phase's implementation contract per worker packet.
- To achieve formal PASS: provision the FFmpeg 8.x shared build DLLs (62/62/60) next to the recorder binary (or set `WINDAGENT_LIBAV_DIR`), re-run `cargo test --lib muxer::libav::tests::keyframe_flag_reaches_mkv_simpleblock -- --nocapture` until it produces `SimpleBlocks read back: key=1 nonkey=2` and `with_audio key=7 nonkey=2`, then run `ffprobe -show_format -show_streams` on each created `segment_*.mkv` and record valid Matroska, codec, FPS, duration, and EBML walker keyflag counts.

## 9. Verdict (advisory, within this evidence file)

`BLOCKED` — Implementation-ready for native MKV with correct B-frame PTS/DTS semantics (lifecycle correct, per-track DTS monotonic with zero valid, DTS<=PTS, PTS preserved verbatim via rescale, header→packets→trailer→fsync→rename, fail-closed guards, 36 muxer tests + 136 total PASS, valid B-frame accepted, invalid DTS rejected) but formal PASS blocked by **NOT_VERIFIED** real Libav-produced MKV ffprobe (missing shared DLLs; not simulated) plus inherited Phase-4 30-minute soak NOT_VERIFIED.

