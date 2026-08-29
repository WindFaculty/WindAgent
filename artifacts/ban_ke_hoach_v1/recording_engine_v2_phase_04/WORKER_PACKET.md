# Phase 4 — Direct NVENC

## Mission

Complete and validate the native NVENC path that accepts the Phase-3 D3D11 texture directly and emits valid H.264 or HEVC Annex-B packets. The encoder must use the shared Phase-2 D3D11 device, a frozen quality-first CQP profile, and must fail closed when NVENC is unavailable or an API call fails. This phase excludes WGC capture, MKV muxing, audio, preview, service cutover, Tauri, and frontend changes.

## Context and baseline

Phase 3 is **IMPLEMENTATION_READY**, not production-certified: its five-minute real 1080p60 WGC soak remains in `artifacts/ban_ke_hoach_v1/UNRESOLVED_GATES.md`. Phase 4 depends on the verified texture-handle and shared-device contract, not that soak, so it may proceed. Phase 5 consumes encoded packets for MKV; Phase 10 composes the encoder into `RecorderService`.

Baseline: `0f869d16cb0bc850d6e5097db0d8bc1089cb9d49`, branch `refactor/architecture-v3-hardening`. Preserve all pre-existing dirty work. Do not touch `artifacts/ban_ke_hoach_v1/phase_04/` or `PHASE_04_REPORT.md`; they are unrelated Statefulness work. Use only this directory for recording-engine Phase-4 evidence.

Existing primitives to reuse:

- `capture/d3d11_device.rs` is the sole adapter/device authority.
- `capture/mod.rs::CapturedFrame` owns an `ID3D11Texture2D` handle; no CPU frame buffer may enter this path.
- `encoder/nvenc_api.rs` contains the ABI bindings and API loader: API instance, session open, initialize, capability probe, register/map/unmap resource, encode, lock/unlock bitstream, sequence params, and cleanup.
- `encoder/nvenc_session.rs::NvencSession` already owns session lifecycle, per-texture registration cache, packet lock/drain/flush, and quality profile construction. `encode_texture` currently calls `input_mapping` → `encode_picture` → `lock_packets` and release/unmap handling.
- `encoder/nvenc_encoder.rs::NvencEncoder` adapts it to `EncoderPort`; `service.rs::build_native_ports` already injects the Phase-2 D3D11 device.
- The FFmpeg capture backend is development-only and forbidden in production path.

Baseline tests: `encoder::nvenc_api` has 11 ABI/loader tests passing. Five `encoder::nvenc_session` tests are ignored manual driver diagnostics, including a synthetic-D3D11 production encoding probe. Do not represent ignored tests as hardware proof.

## Required implementation

1. Inspect current API/session/adapter code and determine what is already correct, incomplete, or misleading. Implement only genuine Phase-4 gaps; do not duplicate the encoder or device authority.
2. Preserve direct resource flow: the same D3D11 texture is registered/mapped to NVENC; no `ID3D11DeviceContext::Map`, staging texture, CPU RGBA buffer, or FFmpeg fallback before `NvEncEncodePicture`.
3. Ensure lifecycle cleanup is exact: a texture’s registered/mapped resource is released on successful output, buffered `NEED_MORE_INPUT`, encode error, flush, drop, and resolution/session replacement. Do not leak mapped/registered resources or bitstream locks.
4. Implement/fix fail-closed behavior: missing `nvEncodeAPI64.dll`, old/incompatible driver, unsupported codec/capability, invalid dimensions/profile, registration/map/encode/lock errors must surface contextual `NVENC_*` errors and never silently software encode or lower the active take’s profile.
5. Respect frozen quality settings: H264/HEVC, CQP, CQ, P5/P6/P7, multipass, lookahead, AQ, B-frames, GOP. Optional driver-unavailable knobs may be disabled only with explicit capability-driven behavior; no automatic quality downshift during a take. Expose warning/probe truth rather than fabricate support.
6. Ensure packets are usable by Phase 5: packet data is actual Annex-B output, PTS remains the Phase-3 QPC-derived microsecond timeline, IDR request is honored, sequence params are obtained before the first muxed packet, and flushing drains delayed B-frame/lookahead output.
7. Make hardware diagnostics deterministic and honest. A synthetic 1920x1080 D3D11 texture hardware probe may be run only if it is already in code and does not capture the user’s screen. It must report actual runtime result; unavailable hardware/driver is a HARDWARE gate blocker, not PASS. Do not run the 30-minute stall gate unless it can be safely automated; record it as NOT_VERIFIED otherwise.

## Authorities and invariants

| State | Authority |
| --- | --- |
| D3D11 device and adapter | `capture/d3d11_device.rs` / injected shared device |
| Capture texture | Phase-3 `CapturedFrame` |
| Encoder lifecycle and resource cache | `NvencSession` |
| ABI/API function table | `NvencApi` |
| Profile | frozen `RecordingProfile` mapped through existing `NvencConfig` |
| PTS | Phase-3 QPC timeline |

Non-negotiable invariants:

- No CPU copy/readback/software/FFmpeg fallback on the production WGC→NVENC path.
- The registered texture belongs to the same shared D3D11 device; no second authority/device.
- Every registered resource is unmapped/unregistered exactly once at appropriate lifecycle boundary; encode errors cannot retain an authoritative mapping.
- `NEED_MORE_INPUT` is buffered output, not an error or dropped frame; `flush` drains it.
- A stale/error session cannot emit a packet after teardown; drop/flush are safe and do not leak driver handles.
- Profile never silently degrades during a take; unsupported optional feature is capability-reported.

## Failure, idempotency, and concurrency

NVENC session and its D3D11 resource cache are single encode-thread owned. Do not make them global or `Sync` as a session. Calls after EOS must fail deterministically. Repeated flush/drop must be safe; resource cleanup must be idempotent. This phase introduces no durable state, database mutation, retry ledger, lease, or transaction.

## Tests and gates

Classify before running:

- UNIT: ABI struct/version/status/cap tests, config matrix, resource-cache/error cleanup tests.
- INTEGRATION: EncoderPort ↔ NvencSession packet/flush behavior where hardware is available.
- HARDWARE: synthetic D3D11 texture → NVENC → nonempty valid Annex-B stream.
- PERFORMANCE/SOAK: 30-minute no-stall gate (NOT_VERIFIED unless actually observed).

Run and report exact results for:

```text
cargo test --manifest-path apps/desktop/native/recording-engine/Cargo.toml encoder::nvenc_api --lib
cargo test --manifest-path apps/desktop/native/recording-engine/Cargo.toml encoder:: --lib
cargo check --manifest-path apps/desktop/native/recording-engine/Cargo.toml
```

Run an existing ignored synthetic hardware probe only if safe; report its actual output/status separately. Add targeted tests for any changed cleanup/failure/capability semantics and inspect source for `Map`, staging/readback, CPU frame bytes, or production FFmpeg fallback.

## Pre-mortem / forbidden shortcuts

Do not: count ignored hardware tests as passing; report NVENC availability solely from successful compilation; replace NVENC with FFmpeg/software encoder; build a second D3D11 device; hide `NEED_MORE_INPUT`; forget map/unmap/unregister cleanup on error; downgrade profile automatically; claim 30-minute no-stall evidence without running it; alter WGC, muxer, audio, preview, RecorderService, Tauri/frontend, existing dirty files, or unrelated phase artifacts.

## Evidence and completion

Create `EVIDENCE.md`, `PHASE_04_REPORT.md`, and `phase_04_verdict.json` in this directory. Classify each important claim as OBSERVED, STATICALLY_VERIFIED, INFERRED, or NOT_VERIFIED. Include baseline/final SHA and scoped dirty status, changed files, tests and counts, all hardware/performance gates, first-pass self-assessment, and advisory verdict.

Implementation-ready completion requires direct texture lifecycle, quality/profile behavior, error semantics, focused tests, `cargo check`, no duplicate authority, and truthful evidence. Formal PASS additionally requires the real direct-texture hardware Annex-B probe and 30-minute no-stall gate; otherwise verdict must be BLOCKED despite implementation readiness.

## Mandatory worker self-review

Before handoff, answer: (1) full requirements; (2) partial requirements; (3) architecture assumptions; (4) duplicate authority; (5) crash/restart paths; (6) concurrency paths; (7) previous-phase tests; (8) required tests not run; (9) risks; (10) whether PASS is justified. Inspect → implement → test → repair own failures → retest → evidence → complete handoff; do not stop at analysis.
