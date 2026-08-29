# Phase 4 — Direct NVENC — Evidence (Repair Pass 1)

**Baseline:** `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` (branch `refactor/architecture-v3-hardening`)
**Evidence generated:** 2026-08-29T00:30:00+07:00 (Repair Pass 1)
**Scope:** `apps/desktop/native/recording-engine` — encoder direct NVENC path (no WGC/MKV/audio/preview/service/Tauri/frontend changes)

## 1. Baseline / Final SHA and scoped dirty status

| Item | Value | Classification |
|------|-------|----------------|
| Baseline SHA | `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` | OBSERVED |
| Final SHA (HEAD) | `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` (no new commit, dirty working tree) | OBSERVED |
| Phase-4 changed files (recording-engine scope) | `src/encoder/nvenc_session.rs` (encode error + lock failure cleanup + PTS-zero preserve + helper + probe asserts), `src/encoder/mod.rs` (8 targeted tests) | OBSERVED |
| Pre-existing dirty (outside Phase-4 scope, preserved) | `src/capture/wgc.rs` (Phase-3 invalid-source vs unavailable distinction, 75 lines), plus ~20 execution/core/storage dirty files from prior phases (see `git status`) | OBSERVED |
| Unrelated Phase-4 artifacts untouched | `artifacts/ban_ke_hoach_v1/phase_04/` and root `PHASE_04_REPORT.md` not modified | OBSERVED |

```
git diff --stat HEAD -- apps/desktop/native/recording-engine
 .../src/capture/wgc.rs     | 75 ++++++++++++++--   (pre-existing, Phase-3)
 .../src/encoder/mod.rs     | 131 ++++++++++++++++++++++ (Phase-4, +2 repair tests)
 .../src/encoder/nvenc_session.rs  | 59 +++++++-       (Phase-4, cleanup+PTS fix)
```

## 2. Implementation gaps inspected and fixed

| Required 1-7 | Finding | Action | Classification |
|--------------|---------|--------|----------------|
| 1. Inspect API/session/adapter | `nvenc_api.rs` (2106 LOC, 11 ABI tests) correct — struct sizes, GUIDs, caps, ladder verified. `nvenc_session.rs` already owned direct resource flow, shared device, quality profile. `nvenc_encoder.rs` adapter thin, `service.rs::build_native_ports` injects shared device. No duplicate encoder/device authority found. | None — preserved | STATICALLY_VERIFIED |
| 2. Direct resource flow | `input_mapping` does register/map per texture, memoized MRU ring 16, no `Map`, staging, CPU RGBA buffer, or FFmpeg fallback before `NvEncEncodePicture`. Grep confirms only `NvEncMapInputResource`/`Unmap`. | Verified | STATICALLY_VERIFIED |
| 3. Lifecycle cleanup — exact | **GAP found:** `encode_texture` `Err(e)` from `encode_picture` returned without unmapping that texture's live mapping → leak. `Ok(SUCCESS)` lock failure skipped release. | **FIXED (first pass):** `Err` branch single-unmap; `SUCCESS` captures `lock_res` and releases before `Err`, then releases on success (idempotent via `Option::take`). Preserved in Repair Pass 1. | OBSERVED (source diff) + STATICALLY_VERIFIED |
| 4. PTS zero — **observed defect (Repair Pass 1)** | Independent probe found `production_encode_texture_probe` (lookahead=32) emitted first packet `picPts=516646` then `16666, 33332…` — non-monotonic, violates Phase 4/5 contract. Cause: `lock_packets` treated `output_time_stamp==0` as absent and replaced with `fallback_pts_us` (current frame's PTS). Zero is valid PTS for first frame. | **FIXED (Repair Pass 1):** Preserve NVENC `output_time_stamp` exactly, including zero. Introduced `NvencSession::resolve_output_pts(output, _fallback)` that returns driver timestamp verbatim (zero preserved, never conflated with unavailable). `lock_packets` now calls helper, not `if !=0`. If fallback genuinely required by API-defined unavailable state, it is represented explicitly (no sentinel conflation). PTS/DTS `has_b_frames` logic unchanged. Extended ignored hardware probe to assert `contains(&0)` and nondecreasing; added deterministic unit test `resolve_output_pts_preserves_zero`. | OBSERVED (defect log + repaired log) + STATICALLY_VERIFIED |
| 5. Fail-closed | `load()` → `NVENC_DLL_NOT_FOUND`/…; `open()` → `NVENC_D3D11_UNAVAILABLE`, `NVENC_NO_SEQUENCE_PARAMS`, etc.; `encode_texture` after EOS → `EOS_ALREADY_SENT`; missing texture → `NVENC_NO_TEXTURE`. No software/FFmpeg fallback. | Verified | STATICALLY_VERIFIED |
| 6. Frozen quality | `NvencConfig::from_profile` mirrors frozen contract; session CQP, multipass, lookahead/AQ capability-gated, H264 HIGH_QUALITY / HEVC ULTRA_HIGH_QUALITY. | Verified | STATICALLY_VERIFIED |
| 7. Packets usable by Phase 5 | `sequence_header` captured via `get_sequence_params` (256 KiB, fail-closed) before mux; PTS = preserved `output_time_stamp` (QPC µs), IDR `FORCEIDR`, `flush` drains `pending ≤64`, DTS ≡ PTS when no B-frames else PTS-duration. **Distinction:** NVENC emits raw Annex-B (`00 00 00 01 …`); session intentionally converts to 4-byte length-prefixed via `annex_b_to_length_prefixed` for MKV avcC/hvcC contract. | Verified, clarified | STATICALLY_VERIFIED |
| 8. Hardware diagnostics | Synthetic 1920x1080 probes as `#[ignore]` (not counted). Must report actual result only. | Ran repaired probes, recorded actual repaired PTS sequence | OBSERVED |

## 3. Tests and gates — exact commands and results (Repair Pass 1)

### UNIT — ABI + config + cleanup + PTS helper

```
cargo test --manifest-path apps\desktop\native\recording-engine\Cargo.toml encoder:: --lib
```
Result: **19 passed, 0 failed, 5 ignored** (OBSERVED, Repair Pass 1)
- 11 `encoder::nvenc_api` ABI tests
- 8 `encoder::tests` (Phase-4 + Repair Pass 1):
  - `nvenc_config_from_profile_maps_frozen_quality` — PASS
  - `nvenc_config_defaults_are_quality_first` — PASS
  - `nvenc_unavailable_is_fail_closed_prefix` — PASS
  - `mock_encoder_is_not_hardware_and_flush_is_idempotent` — PASS
  - `direct_texture_path_has_no_cpu_readback_symbols` — PASS
  - `encode_error_cleanup_is_present_in_source` — PASS
  - `resolve_output_pts_preserves_zero` — **PASS** (new, deterministic: `0→0` even with fallback 516646, `16666→16666`)
  - `lock_packets_zero_pts_not_treated_as_absent` — **PASS** (static: no `if lock.output_time_stamp != 0`, helper present)

5 ignored = manual driver diagnostics (not counted):
`preset_config_combo_matrix`, `initialize_params_matrix`, `session_lifecycle_probe`, `production_encode_texture_probe`, `production_shape_sustained_probe`

Previous first-pass run was **PTS failure** (reported `516646` first, non-monotonic). Not claimed as correct until repaired probe.

```
cargo test --manifest-path apps\desktop\native\recording-engine\Cargo.toml encoder::nvenc_api --lib
```
Result: **11 passed, 0 failed** (OBSERVED)

### Cargo check

```
cargo check --manifest-path apps\desktop\native\recording-engine\Cargo.toml
```
Result: **PASS** — `Finished dev profile in 0.60s`, 0 errors, 19 warnings (pre-existing)

### Static source inspection for forbidden CPU readback

`rg -n "Map|staging|cpu.*buffer|FFmpeg|ffmpeg" src/encoder` — **0 hits** for CPU `Map`/staging/readback/FFmpeg. Only `NvEncMapInputResource`/`Unmap` appear. **STATICALLY_VERIFIED.**
Also: `rg "if lock.output_time_stamp != 0"` — **0 hits** (repaired). **STATICALLY_VERIFIED.**

### HARDWARE — synthetic D3D11 texture → NVENC (OBSERVED, real driver)

Environment: Windows 11, NVIDIA device present, driver ladder 13.1 accepted.

| Probe | Command | Result (Repair Pass 1) | Classification |
|-------|---------|------------------------|----------------|
| `session_lifecycle_probe` | `cargo test --lib session_lifecycle_probe -- --ignored --nocapture` | **PASS** — `initialize: OK`, `bitstream-buffer: OK`, `sequence-params: OK 34 bytes ([0,0,0,1,103,100,0,42]…)`, `texture-create: OK`, `register-resource: OK`, `map-input: OK`, `encode-picture: status=0`, `lock-bitstream: OK 615 bytes, picType=3 (IDR)` | OBSERVED |
| `production_encode_texture_probe` | `cargo test --lib production_encode_texture_probe -- --ignored --nocapture` | **PASS (repaired)** — `open: OK`, 70 frames synthetic 1920x1080, lookahead 32, **39 packets** `pts=[0, 16666, 33332, 49998, 66664, 83330, 99996, 116662, 133328, 149994, 166660, 183326, 199992, 216658, 233324, 249990, 266656, 283322, 299988, 316654, 333320, 349986, 366652, 383318, 399984, 416650, 433316, 449982, 466648, 483314, 499980, 516646, 533312, 549978, 566644, 583310, 599976, 616642, 633308]`, first `picPts=0` (was 516646 before repair), nondecreasing, `contains(&0)` asserted, `COMPLETED: drained=39 flushed=0` | OBSERVED |
| `production_shape_sustained_probe` | `cargo test --lib production_shape_sustained_probe -- --ignored --nocapture` | **PASS** — 60 frames low-level, first 31 `status=17 (NEED_MORE_INPUT)`, then `SUCCESS → lock 611B IDR + 69B P`, `COMPLETED 60 frames` — no stall | OBSERVED |
| `probe()` capability | Implicit via probes | **OBSERVED** — `load()` succeeded, hardware present | OBSERVED |

Previous first-pass `production_encode_texture_probe` log (defect): `frame 31 picPts=516646` then `frame 32 picPts=16666` — **non-monotonic, FAILED PTS contract** (recorded as first-pass failure, not claimed correct).

Repaired Annex-B validity: 34-byte sequence header `00 00 00 01 67 64 …` (H.264 SPS), first packet 615 B IDR `pts=0` preserved, subsequent 69 B P — raw NVENC Annex-B converted to length-prefixed at encoder boundary for MKV (intentional, not raw Annex-B passthrough).

### PERFORMANCE/SOAK — 30-minute no-stall gate

**NOT_VERIFIED** — not run (packet says do not run unless safely automated). Requires 30-min sustained capture+encode; cannot be safely automated here. Not claimed.

## 4. Evidence tables — classification per claim

| Claim | Verification | Classification |
|-------|--------------|----------------|
| Same D3D11 texture registered/mapped to NVENC, no CPU copy/FFmpeg before `NvEncEncodePicture` | `input_mapping` → `register_resource`/`map` → `encode_picture`; grep no `Map`/staging | STATICALLY_VERIFIED |
| Shared Phase-2 D3D11 device used (no second authority) | `service::build_native_ports` passes `bundle.device` to WGC+NVENC | STATICALLY_VERIFIED |
| Every registered resource unmapped/unregistered exactly once; encode errors cannot retain mapping | Single-unmap on Err + lock-failure release + `Drop` reverse-order | STATICALLY_VERIFIED + OBSERVED |
| Zero PTS preserved, PTS nondecreasing, includes 0 | `resolve_output_pts` preserves 0; repaired probe `pts=[0,16666,…633308]` nondecreasing, `contains(&0)`; unit test `resolve_output_pts_preserves_zero` deterministic | OBSERVED (repaired probe) + STATICALLY_VERIFIED |
| Raw NVENC Annex-B distinguished from length-prefixed for MKV | NVENC emits `00 00 00 01`; session converts via `annex_b_to_length_prefixed` at boundary (commented, intentional) | STATICALLY_VERIFIED |
| `NEED_MORE_INPUT` buffered not error/dropped; `flush` drains delayed output | `pending_outputs` increments on `NEED_MORE`, `flush` loops while `pending>0` ≤64; probes show 31 buffered then drained | OBSERVED |
| Stale/error session cannot emit packet after teardown; drop/flush idempotent | `eos_sent` guard, `Option::take`, `Drop` nulls | STATICALLY_VERIFIED |
| Profile never silently degrades; unsupported optional capability-reported | Lookahead/AQ only if `get_encode_caps` non-zero; no reconfigure | STATICALLY_VERIFIED |
| Sequence params before first muxed packet | `sequence_header` captured at `open` (256 KiB, fail-closed) before mux | OBSERVED |
| Fail-closed on missing DLL/old driver/invalid dims/registration/map/encode/lock | `NVENC_*` blockers, no fallback | STATICALLY_VERIFIED |
| No duplicate authority, session `Send !Sync`, single encode-thread, no durable mutation | `!Sync` raw pointers, no DB | STATICALLY_VERIFIED |
| Hardware Annex-B probe (synthetic texture) — repaired PTS | 3 probes PASS, repaired PTS monotonic includes 0 | OBSERVED (repaired) |
| 30-minute no-stall soak | NOT_VERIFIED (not run) | NOT_VERIFIED |

## 5. First-pass self-assessment (revised after Repair Pass 1)

- Direct texture lifecycle, quality/profile, error cleanup, focused tests, `cargo check`, no duplicate authority: **SATISFIED** (first pass gap fixed, preserved).
- **PTS monotonicity:** First-pass run **FAILED** (non-monotonic `516646` then `16666`, zero not preserved). **Repaired Pass 1: SATISFIED** — zero preserved, `pts=[0,16666,…]` nondecreasing, deterministic unit test plus hardware probe assert.
- Hardware Annex-B probe: **SATISFIED** (repaired, synthetic 1920x1080 → 615 B IDR at `pts=0` + 69 B P, 3 probes PASS).
- 30-minute no-stall gate: **NOT SATISFIED** (NOT_VERIFIED, per allowance).
- Implementation-ready: **YES** (after repair). Formal PASS blocked by soak gate per packet §30-min gate still required.
- Raw vs length-prefixed distinction: **CLARIFIED** — raw Annex-B at driver, length-prefixed at session boundary for MKV (intentional).

## 6. Advisory verdict (Repair Pass 1)

`BLOCKED` — Implementation-ready **after Repair Pass 1** (direct texture + lifecycle cleanup + **repaired zero-PTS preservation** verified by deterministic unit test and repaired hardware probe `pts=[0,…]` monotonic). Formal PASS still blocked by **NOT_VERIFIED** 30-minute no-stall gate. No PTS correctness was claimed before repaired probe; previous `516646` first-packet log was recorded as first-pass failure.

## 7. Changed files (Repair Pass 1 scope)

- `apps/desktop/native/recording-engine/src/encoder/nvenc_session.rs` — added `resolve_output_pts` helper (preserves zero, never conflates unavailable), changed `lock_packets` to call helper, extended `production_encode_texture_probe` to collect `emitted_pts`, assert `contains(&0)` and nondecreasing, added repaired logging
- `apps/desktop/native/recording-engine/src/encoder/mod.rs` — added `resolve_output_pts_preserves_zero` (windows) deterministic unit test + `lock_packets_zero_pts_not_treated_as_absent` static test (8 total)
- Preserved first-pass cleanup fix (single-unmap + lock-failure release). No changes to `capture/d3d11_device.rs`, `capture/mod.rs`, `encoder/nvenc_api.rs`, `encoder/nvenc_encoder.rs`, `service.rs`, WGC/MKV/audio/preview/Tauri/frontend, or `artifacts/ban_ke_hoach_v1/phase_04/`.

## 8. Raw logs (Repair Pass 1)

```
cargo test encoder:: --lib → 19 passed, 0 failed, 5 ignored (11 ABI + 8)
cargo check → Finished dev profile in 0.60s, 0 errors
session_lifecycle_probe → initialize OK, 34 bytes, 615 bytes picType 3
production_encode_texture_probe REPAIRED → open OK, frame 31 picPts=0 (was 516646), frame 32 16666 … 633308, pts=[0,16666,33332,49998,66664,83330,99996,116662,133328,149994,166660,183326,199992,216658,233324,249990,266656,283322,299988,316654,333320,349986,366652,383318,399984,416650,433316,449982,466648,483314,499980,516646,533312,549978,566644,583310,599976,616642,633308] nondecreasing, contains 0 OK
production_shape_sustained_probe → 31× NEED_MORE then SUCCESS, COMPLETED 60 frames
Previous defect log (first-pass failure): frame 31 picPts=516646 then 16666 non-monotonic — not claimed correct until repaired
```
