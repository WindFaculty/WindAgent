// Live Record — Tauri Control Plane (Phase 0 Frozen)
// Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN
//
// This module OWNS the recorder IPC surface. Recording engine (data plane) lives in
// `apps/desktop/native/recording-engine/` and is NOT inlined here.

pub mod commands;
pub mod engine_host;
pub mod playback;
pub mod state;
#[cfg(test)]
mod tests;
pub mod types;

pub use commands::{
    recorder_create_marker, recorder_get_capabilities, recorder_get_status, recorder_pause,
    recorder_resume, recorder_prepare, recorder_start, recorder_stop,
};
pub use engine_host::{EngineHost, EngineHostState, EventSink};
pub use playback::{playback_execute_code, playback_probe_environment};
pub use state::{can_transition, LiveRecordState, RecorderSharedState};
pub use types::{
    MarkerRequest, NativeCapabilities, RecorderPrepareRequest, RecorderProfile,
    RecorderStartRequest, RecorderStatus,
};

/// Allowed command names — mirrors `RecorderCommand` (+ capability probe) in
/// `frontend/app/src/features/live-record/contracts/ipc.ts`.
/// Enforced by gate tests in `tests.rs`.
pub const ALLOWED_RECORDER_COMMANDS: &[&str] = &[
    "recorder_prepare",
    "recorder_start",
    "recorder_pause",
    "recorder_resume",
    "recorder_stop",
    "recorder_get_status",
    "recorder_create_marker",
    "recorder_get_capabilities",
];
