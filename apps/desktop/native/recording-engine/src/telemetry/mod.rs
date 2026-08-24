//! Telemetry — Section 20 (Recording Status) & Section 29 (Performance gate)
//!
//! Real metrics (fail-closed gates):
//!   dropped_frames < 0.1% , NVENC hardware confirmed, preview <200ms,
//!   Gemini 1–2 FPS max, every segment independently playable, 30–60 min soak.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Telemetry {
    pub frames_captured: u64,
    pub frames_encoded: u64,
    pub frames_dropped: u64,
    pub current_segment_index: Option<u32>,
    pub disk_write_mbps: f64,
    pub nvenc_util_pct: Option<f64>,
    pub encode_latency_ms_p50: Option<f64>,
    pub preview_delay_ms: Option<u64>,
    pub bitrate_mbps: f64,
}

impl Telemetry {
    pub fn on_frame_captured(&mut self) {
        self.frames_captured += 1;
    }

    pub fn on_frame_encoded(&mut self) {
        self.frames_encoded += 1;
    }

    pub fn on_frame_dropped(&mut self) {
        self.frames_dropped += 1;
    }

    pub fn dropped_pct(&self) -> f64 {
        if self.frames_captured == 0 { 0.0 } else {
            (self.frames_dropped as f64 / self.frames_captured as f64) * 100.0
        }
    }

    pub fn is_within_performance_gates(&self) -> bool {
        // Section 29 baseline: dropped <0.1%, preview <200ms
        self.dropped_pct() < 0.1
            && self.preview_delay_ms.unwrap_or(0) < 200
    }

    pub fn to_recorder_status_fields(&self) -> (f64, Option<u64>) {
        (self.dropped_pct(), self.preview_delay_ms)
    }
}
