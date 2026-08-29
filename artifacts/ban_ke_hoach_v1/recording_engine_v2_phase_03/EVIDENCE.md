# Phase 3 — Direct Windows Graphics Capture — Evidence

Baseline commit: `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` on `refactor/architecture-v3-hardening`
Final commit / worktree: same HEAD `0f869d16`, dirty working tree — only `apps/desktop/native/recording-engine/src/capture/wgc.rs` changed for Phase 3 (plus this evidence directory). No reset/clean/checkout/stage of pre-existing dirty work. `artifacts/ban_ke_hoach_v1/phase_03/*` untouched (Stateful Execution).

Generated: 2026-08-28T16:30:00Z (UTC)
Host: Windows. The recorded unit tests branch on `GraphicsCaptureSession::IsSupported()`; no standalone live WGC probe result is asserted here. `shared_device_vendor_derives_from_bound_adapter` verifies consistency between the selected adapter and the injected D3D11 device, not that NVIDIA was selected.
Verdict authority: actual WGC/WinRT/D3D11 APIs — never mock/FFmpeg fallback.

## 1. Files Changed (Phase 3 scope only)

- `apps/desktop/native/recording-engine/src/capture/wgc.rs` — 70 ins / 5 del: repaired invalid-source vs unavailable-host test semantics, added distinct regression coverage for DISPLAY and WINDOW invalid sources. No production implementation change was required; zero-copy pipeline already correct. Production code left intact (prepare/start/poll/stop, FrameQueue, format mapping, enumeration, shared-device, resize/HDR/source-lost handling).
- `artifacts/ban_ke_hoach_v1/recording_engine_v2_phase_03/EVIDENCE.md` — this file (permitted evidence location).

Not touched: `apps/desktop/native/recording-engine/src/capture/mod.rs`, `d3d11_device.rs`, `service.rs`, `Cargo.toml`, encoder/muxer/audio/preview/Tauri/frontend, `artifacts/ban_ke_hoach_v1/phase_03/*`, nor any pre-existing dirty files listed in worktree status.

## 2. Implementation Summary (inspect → repair → retest)

Inspected `wgc.rs` (1534 LOC), `mod.rs` (CapturePort/CapturedFrame), `d3d11_device.rs`, `service.rs::build_native_ports`, `Cargo.toml` features, and existing tests.

Findings:
- DISPLAY and WINDOW pipeline already uses existing direct WGC path: `GraphicsCaptureItem` via `IGraphicsCaptureItemInterop::CreateForMonitor/CreateForWindow` → `Direct3D11CaptureFramePool::CreateFreeThreaded` → FrameArrived → `IDirect3DDevice`/`IDirect3DDxgiInterfaceAccess` → `ID3D11Texture2D` → `CapturedFrame { texture, width, height, format, qpc, frame_number }`. Zero-copy preserved; no `Map`, pixel readback, byte buffer, or FFmpeg fallback in hot path (verified by grep).
- `with_shared_device` reuses Phase-2 `d3d11_device` bundle — no parallel/global device.
- Lifecycle `prepare -> start -> poll_frame -> stop` correct: `poll_frame` drains `FrameQueue` and returns `None` when empty (no busy-wait); `stop` removes `FrameArrived`/`Closed` tokens, closes session/pool, drains queue, resets core, idempotent via atomic flags, stale callbacks cannot re-enqueue authoritative frames (pool closed → TryGetNextFrame error, plus queue clear after token removal).
- Resize/HDR/format: `acquire_one` detects `Format`/`Width/Height` change, `Recreate`s existing pool for new geometry, discards only transitional frame. No new global device/clock/state machine.
- Metadata: dimensions/format from `D3D11_TEXTURE2D_DESC`, QPC from `SystemRelativeTime` converted by `hundred_ns_to_qpc_ticks` (fallback `qpc_now()` only if WGC time absent), monotonic `frame_number` via `frames_arrived` atomic. QPC is sole clock.
- Error semantics: `prepare` checks `os_supports_wgc()` first → `WGC_UNAVAILABLE` if host cannot run WGC; otherwise `resolve_capture_item` → `WGC_ITEM_CREATION_FAILED:<ctx>` (display_not_found / bad_window_token / window_not_found / create_for_...). `CAPTURE_SOURCE_LOST` via `Closed` handler. All fail closed, never fall back.
- Original test `unknown_display_id_fails_closed_with_ctx_error` was environment-dependent: it asserted `WGC_ITEM_CREATION_FAILED` unconditionally. On a host where `IsSupported()==false` it receives `WGC_UNAVAILABLE` instead (baseline: 10 passed, 1 failed). The repaired test asserts the appropriate fail-closed branch on either kind of host.

Minimal repair applied:
- Rewrote `unknown_display_id_fails_closed_with_ctx_error` to assert fail-closed in both branches: `if os_supports_wgc() { WGC_ITEM_CREATION_FAILED } else { WGC_UNAVAILABLE }`, also checks `!is_available()` and `poll_frame().is_none()` remain empty.
- Added `unknown_window_token_fails_closed_with_ctx_error` covering syntactically bad and nonexistent HWND tokens with same branching distinction.
- Added `invalid_source_vs_unavailable_are_distinct_fail_closed_paths` cross-source regression that explicitly names the two paths and ensures `poll_frame`/`pending_frames` stay clean and `backend_name()=="WGC"` with no fallback.

No runtime semantics changed — `prepare` already ordered `IsSupported` before item creation; repair makes tests honestly reflect that.

## 3. Validation Commands — Exact Results

### cargo test capture::wgc --lib
```
running 13 tests
test capture::wgc::tests::frame_queue_clear_drains_without_counting_drops ... ok
test capture::wgc::tests::frame_queue_overflow_drops_oldest_and_counts ... ok
test capture::wgc::tests::invalid_source_vs_unavailable_are_distinct_fail_closed_paths ... ok
test capture::wgc::tests::monitor_enumeration_never_panics_and_entries_are_valid ... ok
test capture::wgc::tests::os_support_probe_is_total ... ok
test capture::wgc::tests::lifecycle_fails_closed_without_wgc ... ok
test capture::wgc::tests::shared_device_vendor_derives_from_bound_adapter ... ok
test capture::wgc::tests::surface_format_codes_round_trip ... ok
test capture::wgc::tests::surface_format_mapping_covers_sdr_and_hdr ... ok
test capture::wgc::tests::unknown_display_id_fails_closed_with_ctx_error ... ok
test capture::wgc::tests::unknown_window_token_fails_closed_with_ctx_error ... ok
test capture::wgc::tests::window_enumeration_never_panics_and_entries_are_valid ... ok
test capture::wgc::tests::window_tokens_must_be_positive_integers ... ok
test result: ok. 13 passed; 0 failed; 0 ignored; 0 measured; 111 filtered out; finished in 0.65s
```
Previously 11 tests; now 13 (2 new). Baseline failing host would have 10 passed 1 failed; after repair both branches pass on either host.

### cargo test capture:: --lib
```
running 15 tests
test capture::d3d11_device::tests::creates_a_real_hardware_device_where_available ... ok
test capture::d3d11_device::tests::vendor_rank_prefers_nvidia_then_amd_then_intel ... ok
test capture::wgc::tests::frame_queue_clear_drains_without_counting_drops ... ok
test capture::wgc::tests::frame_queue_overflow_drops_oldest_and_counts ... ok
test capture::wgc::tests::invalid_source_vs_unavailable_are_distinct_fail_closed_paths ... ok
test capture::wgc::tests::lifecycle_fails_closed_without_wgc ... ok
test capture::wgc::tests::monitor_enumeration_never_panics_and_entries_are_valid ... ok
test capture::wgc::tests::os_support_probe_is_total ... ok
test capture::wgc::tests::shared_device_vendor_derives_from_bound_adapter ... ok
test capture::wgc::tests::surface_format_codes_round_trip ... ok
test capture::wgc::tests::surface_format_mapping_covers_sdr_and_hdr ... ok
test capture::wgc::tests::unknown_display_id_fails_closed_with_ctx_error ... ok
test capture::wgc::tests::unknown_window_token_fails_closed_with_ctx_error ... ok
test capture::wgc::tests::window_enumeration_never_panics_and_entries_are_valid ... ok
test capture::wgc::tests::window_tokens_must_be_positive_integers ... ok
test result: ok. 15 passed; 0 failed; 0 ignored; 0 measured; 109 filtered out; finished in 0.68s
```
Retains queue overflow/clear, format mapping, enumeration, shared-device coverage.

### cargo check
```
Checking windagent-recording-engine v0.2.0
Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.5s
Exit 0 — 19 warnings (pre-existing unused mut cfg / nvenc_session CreateTexture2D Result must be used), none from wgc.rs changes.
```
Non-Windows builds still compile (fallback `WgcCapture` returns `WGC_UNAVAILABLE`).

### Source checks (grep)
- `Select-String` for `\.Map\(|Map\b|Readback|data_len|FFmpeg|ffmpeg` across `wgc.rs` — no CPU Map/readback or production FFmpeg fallback found; only doc comments stating "no FFmpeg fallback" and legitimate `.map()` iterator uses.
- `CapturedFrame` retains `ID3D11Texture2D` handle, not pixel bytes; `has_texture()` checks `texture.is_some()`.
- `SendTexture` / `AgileCell` wrappers remain single justification (free-threaded COM).
- No `data_len` or byte-buffer surrogate reintroduced.

### Physical 1080p60 5-minute gate
**NOT RUN** — intentional environment gate blocker. No actual `WgcCapture::prepare → start → 5-min capture → stop` physical soak was executed in this CI-like worktree; claiming 1080p60 sustained, no RAM growth, or dropped-frame-free would be fabricated. Unit tests prove queue, format, enumeration, device sharing, and fail-closed branching only. A real desktop session with WGC/NVENC/libav and 5-min wall-clock capture on 1080p60 must be run on a physical Windows host with display attached to evidence the roadmap soak.

## 4. Lifecycle / Invariant Checklist

- [x] DISPLAY and WINDOW use existing direct WGC pipeline — yes, via `resolve_capture_item`.
- [x] Texture-handle frames and zero-copy metadata contract preserved — `CapturedFrame` with `texture: ID3D11Texture2D`.
- [x] Phase-2 shared device authority preserved — `with_shared_device` injected by `RecorderService::build_native_ports`.
- [x] Lifecycle/invalidation/resize/format semantics correct — `prepare/start/poll/stop`, `Closed` → source_lost, `Recreate` discards transitional frame.
- [x] Availability vs invalid-source semantics regression-tested — three tests now branch on `os_supports_wgc()`.
- [x] Focused capture tests and cargo check pass — 13/13 wgc, 15/15 capture::, check OK.
- [x] No unrelated dirty work changed — only wgc.rs test section + this evidence.
- [x] Evidence truthfully records environment limitations — physical soak not claimed.

## 5. Environment Blockers

- Physical soak (1080p60 5-min sustained, RAM, FPS) requires real WGC session on hardware display — not attempted in unit-test-only validation.
- The unavailable-WGC branch is asserted conditionally by the focused tests, but no forced-unavailable integration environment was used.

## 6. Known Gaps

- No live capture → NVENC handoff validation (Phase 4 owns).
- No HDR monitor available to trigger `Rgba16Float` path live; format mapping unit-tested only.
- Window close / display disconnect → `CAPTURE_SOURCE_LOST` handler exists and is unit-wired, but not live-tested with real item invalidation (requires interactive close).
- Encoder/muxer/audio/preview/Tauri/frontend per scope exclusion.

## 7. Advisory Verdict

**PASS** (with environment gate notes). Phase-3 Direct WGC backend is complete and correctly distinguishes `WGC_UNAVAILABLE` vs `WGC_ITEM_CREATION_FAILED`, preserves zero-copy texture pipeline, shared device, and lifecycle invariants. Focused regression now covers both branches without weakening contract. Physical 1080p60 soak remains an unmet environment gate and must not be claimed until a real capture session is evidenced.
