# Phase 4 — Direct NVENC

**Roadmap:** ban_ke_hoach_v1.md §8 (recording-engine V2)  
**Baseline commit:** `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` (branch `refactor/architecture-v3-hardening`)  
**Generated:** 2026-08-29T00:30:00+07:00 (Repair Pass 1)  
**Verdict:** `BLOCKED` — Implementation-ready after Repair Pass 1 (repaired zero-PTS, hardware Annex-B probe PASS) but formal PASS blocked by NOT_VERIFIED 30-minute no-stall gate

## 1. Mission

Complete and validate the native NVENC path that accepts the Phase-3 D3D11 texture directly and emits valid H.264 or HEVC Annex-B packets. The encoder must use the shared Phase-2 D3D11 device, a frozen quality-first CQP profile, and must fail closed when NVENC is unavailable or an API call fails. This phase excludes WGC capture, MKV muxing, audio, preview, service cutover, Tauri, and frontend changes.

Phase 3 is IMPLEMENTATION_READY, not production-certified (5-min real 1080p60 WGC soak in `UNRESOLVED_GATES.md`). Phase 4 depends only on the verified `CapturedFrame`/shared-device contract, so it may proceed. Phase 5 consumes encoded packets for MKV; Phase 10 composes into `RecorderService`.

## 2. Baseline and scope

Baseline `0f869d16` preserved. Pre-existing dirty work preserved (notably `capture/wgc.rs` Phase-3 invalid-source vs unavailable distinction + ~20 execution/core/storage files). `artifacts/ban_ke_hoach_v1/phase_04/` and root `PHASE_04_REPORT.md` were not touched (unrelated Statefulness work). Use only `artifacts/ban_ke_hoach_v1/recording_engine_v2_phase_04/` for evidence.

Existing primitives reused: `capture/d3d11_device.rs` sole device authority, `capture/mod.rs::CapturedFrame` with `ID3D11Texture2D`, `encoder/nvenc_api.rs` ABI bindings/loader, `encoder/nvenc_session.rs::NvencSession` lifecycle/cache/packet/lock/quality, `encoder/nvenc_encoder.rs::NvencEncoder` `EncoderPort` adapter, `service.rs::build_native_ports` shared-device injection. FFmpeg capture backend remains dev-only.

## 3. What was already correct, incomplete, or misleading

Inspection of `nvenc_api.rs` (2106 LOC), `nvenc_session.rs` (1375 LOC), `nvenc_encoder.rs`, `d3d11_device.rs`, `capture/mod.rs`, `service.rs`:

| Component | Status | Details |
|-----------|--------|---------|
| `nvenc_api.rs` | **Correct** | Hand-transcribed SDK 13.1 structs (`NV_ENC_INITIALIZE_PARAMS` 1800 B, offsets pinned, `NV_ENC_CONFIG` 3584 B, `FUNCTION_LIST` 2552 B), GUIDs, caps ordinals (0..60), status names, bitfield helpers, version ladder 13.1→12.0, `verify_table` 14 required slots, `load()`/`open_encode_session_ex`/… 11 ABI tests pass. |
| `nvenc_session.rs` — direct flow | **Correct** | Zero-copy DX path: `input_mapping` memo MRU ring 16, `NV_ENC_BUFFER_FORMAT_ARGB`, no `ID3D11DeviceContext::Map`/staging/CPU RGBA/FFmpeg before `NvEncEncodePicture`. Grep confirms. |
| `nvenc_session.rs` — lifecycle | **Incomplete (GAP, first pass)** | `Err` from `encode_picture` returned without unmapping that texture's live mapping → leak. `SUCCESS` lock failure skipped release. **Fixed first pass** (single-unmap + lock-failure release, preserved). |
| `nvenc_session.rs` — PTS | **Defective (first-pass failure, Repair Pass 1)** | `lock_packets` treated `output_time_stamp==0` as absent and substituted `fallback_pts_us` (`frame*16666`). Zero is valid PTS for first frame. Independent probe (lookahead=32) emitted `picPts=516646` then `16666, 33332…` — non-monotonic, violated Phase 4/5 contract. **Repaired:** preserve driver timestamp exactly via `resolve_output_pts`; zero never conflated with unavailable; no sentinel. Probe extended to assert `contains(&0)` and nondecreasing; deterministic unit test added. |
| `nvenc_session.rs` — quality | **Correct** | CQP `qp_inter_p/b/intra` = `cq` clamp 0..51, `multi_pass` map, H264 `HIGH_QUALITY` / HEVC `ULTRA_HIGH_QUALITY`, optional `lookahead`/`spatial_aq`/`temporal_aq` only after `get_encode_caps`, `chroma_format_idc=1` 4:2:0, `repeat_spspps`, GOP `frame_interval_p = b_frames+1`. |
| `nvenc_session.rs` — packets | **Correct but clarified** | `sequence_header` 256 KiB capture at `open` (fail-closed) before mux; PTS = preserved `output_time_stamp` (QPC µs), IDR `FORCEIDR`, `flush` drains `pending≤64`, DTS ≡ PTS when `has_b_frames=false`. Raw NVENC is Annex-B (`00 00 00 01`); session intentionally converts to length-prefixed via `annex_b_to_length_prefixed` for MKV avcC/hvcC (not raw Annex-B passthrough). |
| `nvenc_encoder.rs` | **Correct** | Thin `EncoderPort` over `NvencSession`, rejects `None` texture as `NVENC_NO_TEXTURE`, honors `request_idr`. |
| `service.rs` | **Correct** | `build_native_ports` creates one `D3d11Bundle` and passes to WGC+NVENC — no second authority. |
| Diagnostics | **Correct but ignored** | 5 `#[ignore]` manual diagnostics — never counted as passing. Extended one for PTS regression. |

No duplicate encoder/device authority was introduced.

## 4. Genuine Phase-4 gaps implemented (first pass + Repair Pass 1)

**First pass:** encode error + lock failure cleanup (single-unmap + release before Err).

**Repair Pass 1 — zero PTS preservation:**

Defect (independent probe): `production_encode_texture_probe` lookahead=32 emitted `frame31 picPts=516646` then `frame32 picPts=16666` — non-monotonic because `lock_packets` did `if output_time_stamp !=0 {driver} else {fallback}`; first frame's driver timestamp `0` was treated as absent and replaced with current `fallback` (516646).

Repair:
```rust
// Before (defective):
let pts_us = if lock.output_time_stamp != 0 { lock.output_time_stamp } else { fallback_pts_us };
// After (repaired):
#[inline] pub(crate) fn resolve_output_pts(output_time_stamp: u64, _fallback: u64) -> u64 { output_time_stamp }
let pts_us = Self::resolve_output_pts(lock.output_time_stamp, fallback_pts_us);
```
- Zero preserved, never conflated with unavailable; no API-defined sentinel exists for NVENC output timestamp, so fallback is only for non-Windows stub where driver absent. PTS/DTS `has_b_frames` logic unchanged.
- Extended ignored probe `production_encode_texture_probe` to collect `emitted_pts`, assert `contains(&0)` and `windows(2).all(|w| w[0]<=w[1])`, log full `pts=[0,16666,…]`.
- Added deterministic unit tests: `resolve_output_pts_preserves_zero` (windows) and static `lock_packets_zero_pts_not_treated_as_absent`.

Preserved mapping cleanup fix; no WGC/muxer/service changes.

## 5. Authorities and invariants — verified

| State | Authority | Evidence |
|-------|-----------|----------|
| D3D11 device and adapter | `capture/d3d11_device.rs` + injected shared device | `service::build_native_ports` — one `bundle.device` for WGC+NVENC+preview |
| Capture texture | Phase-3 `CapturedFrame` (`ID3D11Texture2D`) | `encode_texture` takes `&ID3D11Texture2D`, no CPU buffer |
| Encoder lifecycle/resource cache | `NvencSession` | MRU 16, single live map, unmap on error/success/flush/evict/drop |
| ABI/API function table | `NvencApi` | `load()` ladder, `verify_table`, `struct_ver` stamping |
| Profile | frozen `RecordingProfile` via `NvencConfig` | `from_profile` map, `validate()` rejects out-of-range |
| PTS | Phase-3 QPC timeline (zero preserved) | `resolve_output_pts` preserves 0, `encode_texture(pts_us)` echoed verbatim, `TakeClock` in service |

Non-negotiable invariants — all hold (STATICALLY_VERIFIED + OBSERVED with repaired probe):

- No CPU copy/readback/software/FFmpeg fallback on WGC→NVENC path.
- Registered texture belongs to same shared D3D11 device; no second authority/device.
- Every registered resource unmapped/unregistered exactly once; encode errors cannot retain mapping.
- `NEED_MORE_INPUT` is buffered output, not error/dropped; `flush` drains it (31 buffered then drained, repaired pts monotonic).
- Zero PTS is valid and preserved; PTS nondecreasing and includes 0 (repaired probe `pts=[0,16666,…]` OBSERVED).
- Raw Annex-B at driver distinguished from length-prefixed at session boundary for MKV (intentional conversion).
- Stale/error session cannot emit packet after teardown; drop/flush safe, no driver handle leak.
- Profile never silently degrades during take; unsupported optional feature capability-reported.

## 6. Failure, idempotency, concurrency

- NVENC session + D3D11 resource cache are single encode-thread owned. `NvencSession: Send, !Sync` (raw pointers), `unsafe impl Send` only. Not global/`Sync`.
- Calls after EOS fail deterministically: `encode_texture` returns `NVENC_API_FAILED:EOS_ALREADY_SENT`.
- Repeated `flush`/`drop` safe: `release_input_mappings` uses `take()`, `Drop` nulls handles, `pending_outputs==0` early-exit releases.
- No durable state, DB mutation, retry ledger, lease, transaction introduced.

## 7. Tests and gates — exact results (Repair Pass 1)

| Gate | Command | Result | Classification |
|------|---------|--------|----------------|
| UNIT ABI | `cargo test --manifest-path apps/desktop/native/recording-engine/Cargo.toml encoder::nvenc_api --lib` | 11 passed | OBSERVED |
| UNIT full | `cargo test --manifest-path apps/desktop/native/recording-engine/Cargo.toml encoder:: --lib` | **19 passed, 0 failed, 5 ignored** (11 ABI + 8 new, incl. 2 PTS repair tests) | OBSERVED |
| Cargo check | `cargo check --manifest-path apps/desktop/native/recording-engine/Cargo.toml` | PASS (0 errors) | OBSERVED |
| Source scan | `grep Map/staging/FFmpeg` + `grep "if lock.output_time_stamp != 0"` | 0 hits for both; only `MapInputResource`; helper `resolve_output_pts` present | STATICALLY_VERIFIED |
| HARDWARE synthetic | `cargo test --lib session_lifecycle_probe -- --ignored --nocapture` | **PASS** — 34 B SPS/PPS, 615 B IDR, picType 3 | OBSERVED |
| HARDWARE synthetic | `cargo test --lib production_encode_texture_probe -- --ignored --nocapture` | **PASS (repaired)** — 70 frames, 39 packets, **pts=[0,16666,33332,49998,66664,83330,99996,116662,133328,149994,166660,183326,199992,216658,233324,249990,266656,283322,299988,316654,333320,349986,366652,383318,399984,416650,433316,449982,466648,483314,499980,516646,533312,549978,566644,583310,599976,616642,633308]** nondecreasing, `contains(&0)` OK (was `516646` first before repair, FAILED) | OBSERVED |
| HARDWARE synthetic | `cargo test --lib production_shape_sustained_probe -- --ignored --nocapture` | **PASS** — 60 frames, 31×`NEED_MORE` then `SUCCESS`, no stall | OBSERVED |
| PERFORMANCE soak | 30-min no-stall | **NOT_VERIFIED** — not run per packet allowance | NOT_VERIFIED |

New Phase-4 tests (in `encoder::tests`, 8 total):

- `nvenc_config_from_profile_maps_frozen_quality` — frozen CQP/P5/HALF_RES/HEVC map
- `nvenc_config_defaults_are_quality_first` — P7/FULL_RES/H264 defaults
- `nvenc_unavailable_is_fail_closed_prefix` — `NVENC_UNAVAILABLE` no fallback
- `mock_encoder_is_not_hardware_and_flush_is_idempotent` — idempotent flush
- `direct_texture_path_has_no_cpu_readback_symbols` — static grep
- `encode_error_cleanup_is_present_in_source` — static fix presence
- `resolve_output_pts_preserves_zero` — **new (Repair Pass 1, windows deterministic): zero preserved even with fallback 516646**
- `lock_packets_zero_pts_not_treated_as_absent` — **new (Repair Pass 1, static): no `!=0` fallback logic, helper present**

First-pass `production_encode_texture_probe` log (defect, before repair): `frame31 picPts=516646` then `frame32 picPts=16666` — non-monotonic, **FAILED PTS contract** (recorded as first-pass failure, not claimed correct until repaired).

## 8. Evidence and completion

Files created in `artifacts/ban_ke_hoach_v1/recording_engine_v2_phase_04/`:

- `EVIDENCE.md` — updated for Repair Pass 1 (defect, fix, repaired pts sequence, classifications, raw logs)
- `PHASE_04_REPORT.md` — this report (revised)
- `phase_04_verdict.json` — updated for Repair Pass 1 (pts repaired, still BLOCKED for soak)

Implementation-ready completion requires direct texture lifecycle, quality/profile, error semantics, focused tests, `cargo check`, no duplicate authority, truthful evidence: **SATISFIED after Repair Pass 1**. Formal PASS additionally requires real direct-texture hardware Annex-B probe (SATISFIED, repaired PTS monotonic includes 0) **and** 30-minute no-stall gate (NOT_VERIFIED) → verdict `BLOCKED` despite implementation readiness. Raw vs length-prefixed distinction clarified (Annex-B at driver, length-prefixed at MKV boundary).

## 9. Mandatory worker self-review

1. **Full requirements?** All 7 implementation points inspected; lifecycle gap fixed first pass; **PTS zero defect fixed Repair Pass 1** (preserve zero, monotonic, helper, probe asserts).
2. **Partial requirements?** 30-min soak not run → NOT_VERIFIED (explicit, not claimed). First-pass PTS correctness not claimed until repaired probe.
3. **Architecture assumptions?** Single shared D3D11 device (NVIDIA-preferred walk) assumed; probes confirm same device works for register/map/encode. No second device assumed or built.
4. **Duplicate authority?** None. `d3d11_device.rs` remains sole authority; `NvencSession` owns cache, `NvencApi` owns table, `EngineProfile` owns profile.
5. **Crash/restart paths?** `Drop` reverse-order unmap→unregister→destroy_bitstream→destroy_encoder; `flush` idempotent; EOS deterministic; pending bounded 64. No durable state to corrupt.
6. **Concurrency paths?** Session `Send !Sync`, encode-thread owned, single bitstream buffer sync mode (`enable_encode_async=0`). No global/`Sync` session.
7. **Previous-phase tests?** Phase-3 WGC contract still satisfied (shared device). No WGC/MKV/audio/preview/service changes; WGC dirty preserved.
8. **Required tests not run?** 30-min soak not run (recorded NOT_VERIFIED per allowance). All required unit/cargo check/hardware probes run and reported with repaired PTS. Ignored diagnostics not counted as passing.
9. **Risks?** Idle-screen WGC sparse frames + lookahead 32 could delay drain until flush (pending ≤32) — crash-loss window documented, default profile sets lookahead 0. B-frames off avoids Matroska decode-order violation. Thermal pressure during long takes not observed (soak NOT_VERIFIED). PTS repair eliminates timestamp inversion risk for Phase 5 muxer.
10. **Whether PASS is justified?** **No — BLOCKED is correct.** Implementation-ready after Repair Pass 1 and hardware probe PASS with **repaired PTS `pts=[0,16666,…]` monotonic includes 0**, but formal PASS requires 30-min no-stall evidence which is NOT_VERIFIED. Truthful `BLOCKED` despite readiness, per packet. Repair does not satisfy soak gate.
