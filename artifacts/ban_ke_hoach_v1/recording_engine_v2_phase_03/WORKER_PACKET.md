# Phase 3 — Direct Windows Graphics Capture

## Mission

Complete and validate the Direct Windows Graphics Capture (WGC) backend for the native recording engine. It must capture a display or a window as a D3D11 texture handle for later direct NVENC and GPU preview use; it must never turn frames into CPU pixel buffers. This phase excludes NVENC implementation, muxing, audio, preview, RecorderService cutover, Tauri control-plane, and UI work.

## Roadmap dependencies and baseline

`ban_ke_hoach_v1.md` establishes: Phase 0 freezes DISPLAY/WINDOW recording profile; Phase 1 brings the Windows/WinRT dependencies; Phase 2 owns the one shared D3D11 device. Phase 4 will pass the Phase-3 texture directly to NVENC, Phase 9 will create a GPU preview, and Phase 10 will compose all ports in `RecorderService`.

Baseline commit: `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49` on `refactor/architecture-v3-hardening`. The worktree contains extensive pre-existing user work. Preserve every existing dirty file. Do not reset, clean, checkout, stage, revert, or overwrite unrelated work. `artifacts/ban_ke_hoach_v1/phase_03/*` is unrelated Stateful Execution work: do not alter it. This evidence directory is the only permitted Phase-3 artifact location.

Existing primitives to reuse:

- `apps/desktop/native/recording-engine/src/capture/mod.rs`: `CapturePort` and `CapturedFrame`. `CapturedFrame` is the frame-resource contract; retain texture handle/resource, dimensions, format, QPC timestamp, and frame number. Do not reintroduce `data_len` or pixel bytes.
- `apps/desktop/native/recording-engine/src/capture/wgc.rs`: existing WGC implementation using `GraphicsCaptureItem`, `Direct3D11CaptureFramePool`, capture session, frame callback/queue, source resolution, WGC item acquisition, format and resize handling.
- `apps/desktop/native/recording-engine/src/capture/d3d11_device.rs`: Phase-2 device authority. `WgcCapture::with_shared_device` must reuse it; no parallel device or global device authority.
- `apps/desktop/native/recording-engine/src/service.rs::RecorderService::build_native_ports`: already builds the preferred device and injects it into `WgcCapture`; do not redesign this service or later-phase dependencies.
- `Cargo.toml` already includes the necessary WGC/D3D11/DXGI/COM/WinRT APIs.

Observed baseline command:

```text
cargo test --manifest-path apps/desktop/native/recording-engine/Cargo.toml capture::wgc --lib
10 passed, 1 failed
```

The failing test `unknown_display_id_fails_closed_with_ctx_error` expects invalid-source item creation error, but this host reports `WGC_UNAVAILABLE: Windows Graphics Capture unavailable on this host — recording blocked` first. Repair the test/runtime semantics honestly; do not hide or weaken the actual contract.

## Required implementation

1. Inspect the WGC implementation and existing tests. Repair only genuine Phase-3 defects or test-environment assumptions.
2. Support only `DISPLAY` and `WINDOW`, never camera/webcam or FFmpeg production fallback. A bad/missing/closed source must fail closed with contextual error if WGC is usable. A host with unavailable WGC must fail closed as `WGC_UNAVAILABLE`; tests must distinguish these cases explicitly.
3. Preserve event-driven lifecycle: `prepare -> start -> poll_frame -> stop`. Empty polling must not busy-wait. Stop/teardown must be idempotent and no stale callback may authoritatively enqueue after it.
4. Preserve zero-copy: acquisition hands `ID3D11Texture2D` (or its safe wrapper) to `CapturedFrame`. No CPU `Map`, readback, pixel clone, or byte-buffer surrogate in WGC capture path.
5. Correctly handle resolution/window resize, HDR/SDR format changes, display disconnect, window close and item invalidation. Recreate only the existing frame pool when needed and discard only transitional frame(s). No new global device/clock/state machine.
6. Preserve metadata: source dimensions, known format, WGC composition-time QPC timestamp where available, monotonically increasing frame number. QPC remains the only clock authority.
7. Add/adjust focused regression tests proving availability-vs-invalid-source semantics and retain existing queue, format, enumeration, and shared-device coverage.

## Source-of-truth rules

| State | Authority |
| --- | --- |
| Capture selection | frozen `RecordingProfile.capture_source` |
| GPU adapter/device | Phase-2 `d3d11_device` bundle / injected device |
| Frame resource | existing `CapturedFrame` texture-handle contract |
| Frame timing | WGC `SystemRelativeTime` converted by existing QPC clock |
| Service lifecycle | existing `RecorderService`; no WGC duplicate state machine |
| Availability | actual WGC/Windows APIs; never a mock/FFmpeg fallback |

## Non-negotiable invariants

- WGC capture remains zero-copy and texture based.
- An injected shared D3D11 device remains the same device that later phases can give NVENC.
- WGC unavailable, invalid DISPLAY/WINDOW token, item invalidation, source loss, and unsupported format all fail closed with meaningful distinction; none falls back.
- After stop, stale callbacks cannot restore authoritative capture.
- Every emitted frame has texture, non-zero geometry, known format, QPC timestamp, and increasing sequence.

## Lifecycle and error semantics

| Current | Event | Result |
| --- | --- | --- |
| new | prepare + available valid source | prepared |
| prepared | start | capturing |
| capturing | frame arrival | enqueue texture handle and metadata |
| capturing | size/format change | recreate pool and discard transitional frame |
| capturing | source invalidated | source-lost error, stop emitting |
| capturing | stop | detached/stopped safely |
| any | unavailable WGC / invalid source | fail closed, no fallback |

Phase 3 owns no persistent state, retries, leases, or transaction mechanism; do not add any.

## Backward compatibility and boundaries

Keep `CapturePort`, `CapturedFrame`, profile source shape, and `RecorderService` call pattern compatible. Non-Windows builds must still compile and fail closed with `WGC_UNAVAILABLE`. Do not alter unrelated dirty work, Stateful Execution files/artifacts, FFmpeg development comparator code, encoder/muxer/audio/preview/Tauri/frontend modules, except a strictly necessary Phase-3 integration correction.

## Tests and evidence

Run and report exact results for:

```text
cargo test --manifest-path apps/desktop/native/recording-engine/Cargo.toml capture::wgc --lib
cargo test --manifest-path apps/desktop/native/recording-engine/Cargo.toml capture:: --lib
cargo check --manifest-path apps/desktop/native/recording-engine/Cargo.toml
```

Focused tests must distinguish unavailable host from invalid source and preserve queue overflow/clear, format mapping, enumeration, shared-device behavior. Inspect the changed WGC source to prove no CPU readback (`Map`/pixel buffer) or FFmpeg fallback was added. If this host supports a safe existing WGC probe/capture helper, run it. Never claim the roadmap’s 1080p60 five-minute physical capture, no RAM growth, or sustained 60 FPS without actual evidence; call it an environment gate blocker.

## Pre-mortem and forbidden shortcuts

Do not: merely change an assertion so invalid-source behavior is untested; mask unavailable WGC as valid; reintroduce CPU frame copying; silently fall back to FFmpeg/mock/camera; create another D3D device; redesign RecorderService; claim a unit test proves physical soak; touch user dirty work; fabricate evidence.

## Completion criteria

- [ ] DISPLAY and WINDOW use existing direct WGC pipeline
- [ ] Texture-handle frames and zero-copy metadata contract preserved
- [ ] Phase-2 shared device authority preserved
- [ ] Lifecycle/invalidation/resize/format semantics correct
- [ ] Availability vs invalid-source semantics regression-tested
- [ ] Focused capture tests and cargo check pass
- [ ] No unrelated dirty work changed
- [ ] Evidence truthfully records environment limitations

## Work method and self-review

Inspect, implement, test, repair your own failures, retest, and then hand off. Do not stop after analysis and do not request approval.

In your final response answer exactly:

1. What requirements are fully implemented?
2. What requirements may only be partially implemented?
3. What architecture assumptions were made?
4. Did I introduce any duplicate authority?
5. What restart/crash paths were tested?
6. What concurrency/race risks remain?
7. Which previous-phase tests were executed?
8. Which tests were not executed and why?
9. What known gaps remain?
10. Is PASS actually justified?

Also include: baseline SHA, final SHA/worktree status, changed files, implementation summary, exact test counts/failures/skips, architecture/source checks, environment blockers, known gaps, and one advisory verdict: PASS, FAIL, BLOCKED, or PARTIAL.
