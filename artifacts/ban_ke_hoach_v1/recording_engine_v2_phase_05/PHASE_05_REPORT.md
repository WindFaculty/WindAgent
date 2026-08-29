# Phase 5 — Native MKV / libavformat (Repair 1)

**Roadmap:** ban_ke_hoach_v1.md §9 (recording-engine V2)  
**Baseline commit:** `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` (branch `refactor/architecture-v3-hardening`)  
**Generated:** 2026-08-28T23:45:00+07:00  
**Verdict:** `BLOCKED` — Implementation-ready after Repair 1 (B-frame PTS/DTS preserved, DTS monotonic per-track, valid B-frame accepted) but formal PASS blocked by NOT_VERIFIED real Libav MKV ffprobe (no shared DLLs on host) and inherited 30-minute soak gate

## 1. Mission

Implement or complete the real native `LibavMuxer` path required by ban_ke_hoach_v1.md §9: mux Phase-4 encoded H.264/HEVC length-prefixed packets (avcC/hvcC) plus AAC into independently playable, segmented MKV files using libavformat APIs — never an FFmpeg CLI recorder. Phase 4 is implementation-ready after repair (Annex-B at driver, length-prefixed at session boundary for avcC/hvcC, PTS zero preserved and monotonic when B-frames disabled, but `VideoConfig.b_frames` (0..4) and `NvencSession` has_b_frames DTS logic are exposed and must be preserved). Phase 4's 30-minute soak remains an unresolved production gate but does not block this phase per packet.

## 2. Baseline and scope

Baseline `0f869d16` preserved. Pre-existing dirty work preserved (notably `capture/wgc.rs` Phase-3, `encoder/nvenc_session.rs` + `encoder/mod.rs` Phase-4 zero-PTS repair, plus execution/core/storage dirty from prior phases). This phase touches only `apps/desktop/native/recording-engine/src/muxer/**` and directly necessary shared muxer contract logic. `artifacts/ban_ke_hoach_v1/phase_03` and root `PHASE_04_REPORT.md` were not modified; evidence lives under `artifacts/ban_ke_hoach_v1/recording_engine_v2_phase_05/`.

Existing primitives reused: `muxer/libav_loader::LibavRuntime` shared-DLL loader (WINDAGENT_LIBAV_DIR → exe dir → PATH, families 62/61/60, avutil→avcodec→avformat dependency order, version readback, ABI gate 62/62/60), `muxer/libav::LibavMuxer` segmented writer, `muxer/tracks` avcC/hvcC/AAC ASC builders, `muxer/timestamps` router + monotonic guard, `MuxerPort` trait, mock muxer (dev/CI only).

## 3. What was already correct, incomplete, or misleading — and Repair 1

| Component | Status | Details |
|-----------|--------|---------|
| `libav_loader.rs` | **Correct** | Hand-transcribed 8.1.2 structs (`AVRational` 8B, `AVChannelLayout` 24B, `AVStreamPrefix` 24B, `AVStreamTimingPrefix` 96B, `AVFormatContextPrefix` 56B, `AVCodecParameters` 184B, `AVPacketPartial` 80B), constants (AV_CODEC_ID_H264=27, HEVC=173, AAC=0x15002, ABIs 62/62/60), 19 entry-point signatures, `try_family` loaders, once-lock cache. 5 libav_loader tests PASS. |
| `libav.rs` — FFI lifecycle | **Correct** | `open_native` (`guess_format("matroska")` → `alloc_output_context` → per-track `new_stream` → `AVCodecParameters` fills → `time_base=1/1e6`, `avg_frame_rate` → `packet_alloc` → `avio_open(.tmp)`), `flush_header` (stage `av_mallocz` extradata `avcC/hvcC/ASC` → `avformat_write_header`), `write_native` (`av_new_packet` → memcpy → pts/dts/size/flags/stream_index → `av_packet_rescale_ts` on both fields → `av_interleaved_write_frame` → `av_packet_unref`), `close_native` (header guard → `av_write_trailer` → `avio_closep` → `packet_free`/`free_context` → reopen WRITE → `sync_all` → `rename .tmp→.mkv` → stat). Every negative code routed via `av_strerror` into typed `MKV_*` errors. |
| `libav.rs` — timestamp/contract enforcement | **Incomplete then incorrectly fixed, now REPAIRED** | First Phase-5 pass stored only global `first_pts_us/last_pts_us` with `prev.max(pts)` masking. Second pass added `last_pts_by_slot` and `validate_packet_contract` but blanket-rejected every `dts_us != pts_us` as `MKV_BFRAMES_UNSUPPORTED` with comment “V2 disables B-frames”. This removed the supported `b_frames` profile feature; `NvencSession` explicitly produces `dts = pts - output_duration` when `has_b_frames`. **Repair 1** replaces blanket reject with B-frame-capable validation: `last_dts_by_slot` per slot for written-order DTS monotonic, `DTS<=PTS`, `DTS>=0`, zero valid, PTS preserved verbatim (no written-order PTS monotonic when DTS!=PTS), both rescaled together. `MKV_BFRAMES_UNSUPPORTED` removed, misleading comment removed. |
| `tracks.rs` / `timestamps.rs` | **Correct** | `split_annex_b`, `annex_b_to_length_prefixed`, `build_avcc` (ISO 14496-15), `build_hvcc` (HEVC), `build_aac_asc`, `SegmentRouter` roll logic, `pts_from_micros/micros_from_pts`, `assert_monotonic`. Pure, 13 tests PASS. |
| `muxer/mod.rs` + `mock.rs` | **Correct** | `MuxerPort` prepare/open_segment/stage_video_extradata/stage_audio_extradata/write_packet/close_segment/finalize_take; `LibavMuxer` state machine (`MKV_NOT_PREPARED`, `MKV_SEGMENT_INDEX_REGRESSION`, `MKV_TRACK_LAYOUT_EMPTY`, `MKV_EXTRADATA_MISSING`, etc.), monotonic open guard, mock writer with EBML magic + fsync+rename + recovery contract. |
| ffprobe validation | **Missing runtime** | Host has static `ffmpeg/ffprobe 8.1.2` but no shared `avformat-62.dll/avcodec-62.dll/avutil-60.dll`; `LibavRuntime::load()` correctly returns `LIBAV_UNAVAILABLE: probed 3 location(s) × 3 release family(ies)…` and `keyframe_flag_reaches_mkv_simpleblock` skips. No real `.mkv` produced — not claimed as success. Prior mock `.tmp` probe was not valid evidence and is now marked NOT_VERIFIED. |

No duplicate loader/runtime was introduced; FFmpeg subprocess is never used for recording; mock remains dev-only behind `WINDAGENT_RECORDER_ALLOW_MOCK`.

## 4. Repair 1 — B-frame PTS/DTS semantics

**Gap:** `validate_packet_contract` rejected every `packet.dts_us != pts_us` as `MKV_BFRAMES_UNSUPPORTED` and enforced `this_pts < prev → TIMESTAMP_REGRESSION` in written order. This rejects valid B-frame sequences where PTS in decode order is non-monotonic (e.g., decode I0/P3/B1 has PTS 0,100k,33k) while DTS monotonic (0,33k,50k) is valid. `VideoConfig.b_frames` (0..4) and `NvencSession::has_b_frames` explicitly produce `dts = pts - output_duration` with `DTS <= PTS`. The muxer already passes both fields through `AVPacket{pts,dts}` + `av_packet_rescale_ts`; blanket reject silently removed a supported profile feature.

**Repair:**

```rust
struct SegmentState {
  last_pts_by_slot: Vec<Option<i64>>, // presentation time per slot (preserved verbatim)
  last_dts_by_slot: Vec<Option<i64>>, // decode time per slot — monotonic in written order
}
// Pure helper — testable without handles:
fn validate_packet_contract(seg: &SegmentState, track: TrackId, packet: &EncodedPacket)
  -> Result<(usize,i64), String> {
  slot = slots.position(track)? else MKV_UNKNOWN_TRACK
  if packet.data.is_empty() => MKV_PACKET_EMPTY
  if track==Video && codec not H264|HEVC => MKV_CODEC_MISMATCH
  if track==Mic|System && codec != AAC => MKV_CODEC_MISMATCH
  this_pts = pts_from_micros(pts_us) // >=0
  this_dts = packet.dts_us           // >=0
  if this_dts <0 => TIMESTAMP_INVALID
  if this_dts > this_pts => TIMESTAMP_INVALID (decode after presentation)
  if Some(prev_dts) in last_dts_by_slot[slot] and this_dts < prev_dts => TIMESTAMP_REGRESSION (written-order DTS)
  // PTS preserved verbatim; no PTS monotonic in written order when DTS != PTS (B-frame reorder).
  // When DTS==PTS (no B-frames) DTS monotonic already enforces PTS monotonic in written order.
  Ok((slot, this_pts))
}
fn write_native(...) {
  Self::flush_header(rt, seg)?;
  let (slot_idx, _pts) = Self::validate_packet_contract(seg, track, packet)?;
  // ... size check, av_new_packet, copy, pts=this_pts dts=this_dts flags/stream_index, rescale_ts on both, interleaved_write
  seg.last_pts_us = Some(this_pts) // exact, not max
  seg.last_pts_by_slot[slot_idx] = Some(this_pts)
  seg.last_dts_by_slot[slot_idx] = Some(this_dts)
}
```

- Zero PTS and zero DTS remain valid: `this_dts < prev_dts` is regression, `==` allowed.
- `V2 disables B-frames` comment removed; B-frames are supported via `b_frames` (0..4) and preserved.
- `DTS <= PTS` and `DTS >=0` catch invalid timestamps (e.g., `dts 40k > pts 33k`, negative DTS).
- DTS monotonic per slot in written (decode) order is fail-closed; PTS in decode order may legitimately go backward when B-frames reorder (e.g., `60k → 30k` with DTS `20k → 30k` monotonic) — accepted after Repair.
- `av_packet_rescale_ts` is called with `AVRational{1, TIMEBASE_DEN}` on a packet carrying both pts and dts, so both rescaled together to stream time_base.
- Preserved: all FFI versioning, extradata `av_mallocz`, trailer/fsync/rename, index regression, layout validation, mock, recovery.

Written-order vs presentation-order: **written (decode) order** is the interleaving order fed to `av_interleaved_write_frame`; **presentation order** is sorted by PTS for display. With B-frames, PTS in written order is non-monotonic but presentation-order PTS is monotonic. The muxer enforces DTS monotonic in written order and preserves PTS verbatim; it does not fabricate or max-mask timestamps.

## 5. Authorities and invariants — verified

| State | Authority | Evidence |
|-------|-----------|----------|
| MKV mux + loader | `muxer/libav_loader::LibavRuntime` + `muxer/libav::LibavMuxer` | OnceLock runtime 19 fns, abi_supported gate, 5 loader tests + 10 contract tests |
| CodecPrivate | `muxer/tracks` (avcC/hvcC/ASC) + staged via `set_video/audio_extradata` | `avcC/hvcC` built from `NvEncGetSequenceParams` once per session by `service::build_native_ports`; `collect_audio_asc` per track; `flush_header` stages before `avformat_write_header` |
| PTS/DTS | TakeClock QPC (phase-4 zero preserved) via `EncodedPacket{pts_us,dts_us}` + `NvencSession` has_b_frames | `pts_from_micros` identity, `validate_packet_contract` DTS monotonic + DTS<=PTS, both rescaled together, PTS preserved |
| D3D11/NVENC | Unchanged (phase-4) | Not touched in this phase |

Non-negotiable invariants — all hold (STATICALLY_VERIFIED + OBSERVED):

- No second loader/runtime, no FFmpeg subprocess for recording, mock only behind explicit allow flag.
- Registered AVPacket buffer is owned by libav after `av_new_packet`; `av_interleaved_write_frame` consumes reference, `av_packet_unref` after every attempt.
- Extradata copied into `av_mallocz` buffers because `avformat_free_context` frees `par->extradata` with `av_free` — Rust-owned memory never attached.
- Files write to `{dir}/segment_NNNN.mkv.tmp`, finish (trailer + fsync via WRITE handle) and atomicly rename; any file without `.tmp` is committed (crash-recovery contract).
- Every negative libav return surfaces as typed `MKV_*` or `LIBAV_*` error, never panic.
- `SegmentState::drop` is leak guard only; normal teardown nulls handles first.

## 6. Failure, idempotency, concurrency

- Muxer is single-writer on dedicated mux thread (`pipeline.rs` §3); `LibavMuxer: Send` (raw libav pointers never concurrently accessed). `Encoder` is `Send !Sync`.
- Calls after EOS or without `prepare`/`open_segment` fail deterministically with `LIBAV_UNAVAILABLE` / `MKV_SEGMENT_NOT_OPEN` / `MKV_NOT_PREPARED` / `MKV_SEGMENT_INDEX_REGRESSION` / `MKV_EXTRADATA_MISSING` / `MKV_SEGMENT_EMPTY` / `MKV_CODEC_MISMATCH` / `TIMESTAMP_REGRESSION` / `TIMESTAMP_INVALID` — never panic, never publish partial `.mkv`.
- Repeated `close_segment` without open returns `MKV_SEGMENT_NOT_OPEN`; `finalize_take` with an open segment returns `MKV_SEGMENT_STILL_OPEN`; clean finalize resets `output_dir/last_open_index` for next take.
- No durable state, DB mutation, retry ledger introduced.

## 7. Tests and gates — exact results

| Gate | Command | Result | Classification |
|------|---------|--------|----------------|
| cargo check | `cargo check --manifest-path apps\desktop\native\recording-engine\Cargo.toml` | PASS (0 errors) | OBSERVED |
| muxer filtered | `cargo test --manifest-path apps\desktop\native\recording-engine\Cargo.toml muxer --lib -- --test-threads=1` | **36 passed, 0 failed** (27 pre-existing + 7 first-pass + 3 Repair 1 net new, 1 removed misleading) | OBSERVED |
| full lib | `cargo test --manifest-path apps\desktop\native\recording-engine\Cargo.toml --lib -- --test-threads=1` | **136 passed, 0 failed, 5 ignored** (ignored = NVENC hardware probes) | OBSERVED |
| loader probe | `cargo test --lib muxer::libav_loader::tests::loader_is_total_and_never_panics -- --nocapture` | **PASS** — asserts `LIBAV_UNAVAILABLE` when no DLLs | OBSERVED |
| keyframe walker (real MKV) | `cargo test --lib muxer::libav::tests::keyframe_flag_reaches_mkv_simpleblock -- --nocapture` | **PASS (skipped runtime unavailable, prints 2× "skipping: libav runtime unavailable")** — not claimed as probe PASS | NOT_VERIFIED (expected, DLLs absent) |
| mock ffprobe | `ffprobe -v error -show_streams <mock>.mkv` | `Invalid data found when processing input` (mock is not Matroska) — correctly fails, **NOT_VERIFIED as real validation** | OBSERVED (negative control) |
| real MKV ffprobe | `ffprobe -show_format -show_streams segment_*.mkv` produced by LibavMuxer | **NOT_VERIFIED** — no file exists; `LibavRuntime::load()` fails as described; no simulation | NOT_VERIFIED |
| soak 30-min | Phase-4 gate | NOT_VERIFIED (per UNRESOLVED_GATES.md) | NOT_VERIFIED |

New/updated Phase-5 tests (in `muxer::libav::tests`):

- `timestamp_zero_is_valid_and_monotonic_per_track` — zero PTS/DTS valid per track, DTS monotonic, duplicate allowed, audio independent — PASS
- `valid_bframe_dts_pts_accepted` — `pts 0 dts 0` then `pts 33_333 dts 16_000` (DTS!=PTS) accepted, then `pts 66_666 dts 33_333` accepted, `DTS==PTS` still passes — PASS
- `bframe_reordered_pts_accepted_when_dts_monotonic` — `pts 60_000 dts 20_000` then `pts 30_000 dts 30_000` (PTS backward in written order but DTS monotonic 20k→30k and DTS<=PTS) accepted — PASS
- `rejects_dts_regression_and_invalid_timestamps` — `dts 40_000 < prev 50_000 → TIMESTAMP_REGRESSION`, `dts 40_000 > pts 33_333 → TIMESTAMP_INVALID`, negative `dts -5_000 → TIMESTAMP_INVALID` — PASS
- `rejects_timestamp_regression_per_track` — `dts 40_000 < prev 50_000 → TIMESTAMP_REGRESSION`, forward passes — PASS
- `rejects_codec_mismatch_per_track` — video×AAC and mic×H264 rejected, H264/HEVC/AAC correct passes — PASS
- `rejects_empty_packet_data` — empty vec → MKV_PACKET_EMPTY — PASS
- `rejects_unknown_track` — Mic on video-only segment → MKV_UNKNOWN_TRACK — PASS
- `segmentation_tmp_never_promoted_on_failure` — prepare LIBAV_UNAVAILABLE or empty-segment close leaves no `.mkv` — PASS

Removed: `rejects_bframes_explicitly_v2_contract` (misleading blanket reject) — replaced by B-frame-aware tests above.

## 8. Evidence and completion

Files in `artifacts/ban_ke_hoach_v1/recording_engine_v2_phase_05/`:

- `EVIDENCE.md` — scoped baseline SHA, diff, gap/fix table, 36 muxer + 136 total test receipts, loader + ffprobe blocker, raw logs, NOT_VERIFIED gates, written vs presentation distinction
- `PHASE_05_REPORT.md` — this report
- `phase_05_verdict.json` — machine-readable verdict (BLOCKED but implementation-ready, B-frame preserved, 10 contract tests, loader ffprobe blocker)

Implementation-ready completion requires native lifecycle correct, versioned FFI error-checked, per-track DTS monotonic with zero valid + B-frame DTS<=PTS preserved, PTS verbatim via rescale, extradata handshake, header→interleaved→trailer→fsync→rename, fail-closed typed errors, never-mock-in-production, focused tests, `cargo check`, no duplicate authority, truthful evidence: **SATISFIED**. Formal PASS additionally requires real Libav-produced MKV segments passing `ffprobe` (valid container, H264/HEVC, 60 FPS, monotonic, no corrupt tail) — **NOT_VERIFIED due to missing shared DLLs on this host (static ffmpeg only)** — plus inherited 30-minute soak — hence verdict `BLOCKED` despite readiness.

## 9. Mandatory worker self-review

1. **Full requirements?** All 7 implementation points inspected; native lifecycle verified and hardened with B-frame-aware DTS monotonic + DTS<=PTS validation (Repair 1), misleading B-frame comment removed, 10 focused contract tests, `cargo check` + 136/5 tests PASS, rated blocker for ffprobe with written vs presentation distinction.
2. **Partial requirements?** Real Libav MKV ffprobe NOT_VERIFIED (shared DLLs absent, message reported, not simulated) and 30-min soak NOT_VERIFIED (inherited) — both explicit NOT_VERIFIED per plan, not claimed.
3. **Architecture assumptions?** Shared libav DLLs assumed colocated via `WINDAGENT_LIBAV_DIR`/exe dir/PATH (`avformat-62/avcodec-62/avutil-60` for ABI 62/62/60). Host's static ffmpeg satisfies ffprobe but not loader — reported.
4. **Duplicate authority?** None. `LibavRuntime` remains sole loader (OnceLock), `LibavMuxer` sole segmented writer; `MuxerPort` is still the only muxer port; mock remains dev-only.
5. **Crash/restart paths?** `.tmp` only renamed after trailer+fsync+stat all succeed; empty segment (no header) refused; leak guard `Drop` nulls handles after explicit close; `scan_latest_take`/`recover_take` discard `.tmp` tail.
6. **Concurrency paths?** Muxer confined to single mux thread (`Send` raw pointers, `unsafe impl Send`), encoder `Send !Sync`, no global mutable libav state.
7. **Previous-phase tests?** Phase-3 WGC and Phase-4 NVENC contracts untouched and still pass (WGC 15, NVENC 19 tests including PTS-zero helper, B-frame DTS logic preserved).
8. **Required tests not run?** Real Libav keyframe-walker not run beyond skip (requires shared DLLs); recorded NOT_VERIFIED. All other required unit/cargo check/hardware-probe-equivalent tests run and reported; ignored diagnostics not counted.
9. **Risks?** Idle+lookahead stall, thermal soak, single-bit corruption not covered by single-segment ffprobe — documented; mitigated by chunk+fsync atomicity.
10. **Whether PASS is justified?** **No — BLOCKED is correct.** Implementation-ready after Repair 1 hardening and 36/136 tests PASS with B-frame DTS/PTS preserved and valid reordered PTS accepted, but formal PASS requires real Libav MKV ffprobe evidence which is NOT_VERIFIED on this host due to missing shared DLLs plus 30-min soak NOT_VERIFIED. Truthful `BLOCKED` per packet (do not simulate) and Repair 1 instructions.

