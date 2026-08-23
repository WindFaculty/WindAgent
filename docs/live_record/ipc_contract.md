# IPC Contract — Live Record — Phase 0 Frozen

> Gate: `LIVE_RECORD_P0_ARCHITECTURE_FROZEN` | Code: `frontend/app/src/features/live-record/contracts/ipc.ts` | Rust: `apps/desktop/src-tauri/src/live_record/` (`state.rs`, `types.rs`, `commands.rs`)

## Control Plane (Tauri) — Minimal Surface

Commands (all 8 registered; Rust stubs validate payloads and drive the frozen state machine — see "P0 status" below):

- `recorder_prepare` — binds `execution_plan_hash` to output dir + profile
- `recorder_start`
- `recorder_pause`
- `recorder_resume`
- `recorder_stop` — returns `SegmentManifest`
- `recorder_get_status` — polls telemetry
- `recorder_create_marker`
- `recorder_get_capabilities` — preflight capability probe

Events emitted by native (Phase 8+):

- `recorder://status`
- `recorder://segment`
- `recorder://preview` — **only downsampled preview frames**; raw 1080p60 never crosses IPC
- `recorder://warning`
- `recorder://error`
- `recorder://timeline`

## P0 status (stub semantics)

- Commands exist on both sides and enforce the frozen transition table (`state.rs` mirrors `domain/stateMachine.ts`). `recorder_prepare` fails closed into `BLOCKED` because WGC/NVENC probes are absent until the native engine lands (Phase 8).
- No `recorder://*` event is emitted yet; telemetry counters stay at zero. Real capture/encode/mux lives in the sidecar, never in Tauri.
- Rust-side gate tests: `cargo test live_record --manifest-path apps/desktop/src-tauri/Cargo.toml`.

## Invariants

- Frontend never calls NVENC/libav directly.
- Preview frames: downsampled 1280×720 JPEG/WebP, event-driven or 1–2 FPS max.
- Segment file paths are tokenized (`file_token` / `media_token`) — no raw `D:\...` exposed to UI.
- `NativeCapabilities` check runs in `PREFLIGHT`; `wgc_available`/`nvenc_available` false → `BLOCKED`.
