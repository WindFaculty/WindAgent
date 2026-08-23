//! IPC contract types — mirrors `frontend/app/src/features/live-record/contracts/ipc.ts`.
//! Phase 0 Frozen — Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN.
//!
//! Field names stay snake_case on both sides; Tauri receives the whole payload
//! as a single `request` struct so serde deserializes it 1:1 against the TS interface.

use serde::{Deserialize, Serialize};

use super::state::LiveRecordState;

/// Mirrors `RecorderStatus` in `contracts/ipc.ts`. Telemetry counters stay at
/// zero until the native engine reports real values (Phase 8-9).
#[derive(Debug, Serialize, Clone)]
pub struct RecorderStatus {
    pub state: LiveRecordState,
    pub take_id: Option<String>,
    pub execution_plan_id: Option<String>,
    pub elapsed_sec: u64,
    pub frames_captured: u64,
    pub frames_encoded: u64,
    pub frames_dropped: u64,
    pub dropped_pct: f32,
    pub current_segment_index: Option<u32>,
    pub current_segment_path: Option<String>,
    pub disk_write_mbps: Option<f32>,
    pub nvenc_status: String,
    pub bitrate_mbps: f32,
    pub preview_available: bool,
    pub blockers: Option<Vec<String>>,
}

/// Capability probe for preflight — mirrors `NativeCapabilities` in `contracts/ipc.ts`.
#[derive(Debug, Serialize, Clone)]
pub struct NativeCapabilities {
    pub wgc_available: bool,
    pub nvenc_available: bool,
    /// P0 locked false per Principle F (audio is TTS-generated later).
    pub wasapi_available: bool,
    pub disk_free_gb: f32,
    pub output_writable: bool,
}

// ─── Request payloads — mirror the TS request interfaces ─────────────────────

/// Mirrors `RecorderPrepareRequest` in `contracts/ipc.ts`.
#[derive(Debug, Deserialize, Clone)]
pub struct RecorderPrepareRequest {
    pub execution_plan_id: String,
    pub execution_plan_hash: String,
    pub episode_id: String,
    /// Validated server-side; never echoed back to the UI beyond a token.
    #[allow(dead_code)]
    pub output_dir: String,
    pub profile: RecorderProfile,
}

/// Mirrors the nested `profile` object of `RecorderPrepareRequest`.
#[derive(Debug, Deserialize, Clone)]
pub struct RecorderProfile {
    #[allow(dead_code)]
    pub resolution: String,
    #[allow(dead_code)]
    pub fps: u32,
    #[allow(dead_code)]
    pub codec: String,
    #[allow(dead_code)]
    pub segment_minutes: u32,
    /// Principle F: must be `false` in P0 — enforced fail-closed in prepare.
    pub audio_enabled: bool,
}

/// Mirrors `RecorderStartRequest` in `contracts/ipc.ts`.
#[derive(Debug, Deserialize, Clone)]
pub struct RecorderStartRequest {
    pub execution_plan_id: String,
    pub take_id: Option<String>,
}

/// Mirrors `MarkerRequest` in `contracts/ipc.ts`.
#[derive(Debug, Deserialize, Clone)]
pub struct MarkerRequest {
    pub marker_type: String,
    pub cue_id: Option<String>,
    pub action_id: Option<String>,
}
