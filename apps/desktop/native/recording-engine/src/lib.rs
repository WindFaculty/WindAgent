//! WindAgent Recording Engine - Data Plane (P0 Skeleton)
//! Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN
//!
//! This crate is the data plane. Tauri (apps/desktop/src-tauri) is control plane.
//! P0 ships ONLY contracts + module stubs. Capture/encoder/muxer impl lands Phase 8-9.

pub mod capture;
pub mod encoder;
pub mod muxer;
pub mod segment;
pub mod preview;
pub mod telemetry;
pub mod ipc;

/// P0 engine profile - mirrors contracts/recordingEngine.ts
#[derive(Debug, Clone)]
pub struct EngineProfile {
    pub resolution: (u32, u32),
    pub fps: u32,
    pub codec: String,
    pub segment_minutes: u32,
    pub audio_enabled: bool, // P0 locked: false
}

impl Default for EngineProfile {
    fn default() -> Self {
        Self {
            resolution: (1920, 1080),
            fps: 60,
            codec: "H264".into(),
            segment_minutes: 5,
            audio_enabled: false,
        }
    }
}
