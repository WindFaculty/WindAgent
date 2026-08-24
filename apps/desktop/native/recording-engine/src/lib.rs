//! WindAgent Recording Engine — Data Plane (Phases 8-9)
//! Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN + Phases 8-9 implementation
//!
//! This crate is the **data plane**. Tauri (`apps/desktop/src-tauri`) is the
//! **control plane** — it never touches NVENC/libav directly; it only sends
//! `RecorderPrepareRequest` / `RecorderStartRequest` and receives metrics via IPC.
//!
//! Pipeline (Section 16):
//! ```text
//! Windows Graphics Capture (WGC)
//!           │
//!           ▼
//!        D3D11 texture
//!           │
//!           ├─────────────► Preview Sampler (1–2 FPS, 1280×720 JPEG)
//!           │                   │
//!           │                   ▼
//!           │               Gemini frames (via Tauri preview event)
//!           │
//!           ▼
//!        NVENC (H.264/HEVC)
//!           │
//!           ▼
//!      libavformat (MKV)
//!           │
//!           ▼
//!          MKV segments (take_xxx/segment_xxx.mkv) + timeline.jsonl
//! ```
//!
//! Principle C/D/E/F: raw 1080p60 frames never cross Tauri IPC; recording
//! pipeline is 60 FPS while AI observation is 1–2 FPS downscaled.

pub mod audio;
pub mod capture;
pub mod encoder;
pub mod muxer;
pub mod preview;
pub mod probe;
pub mod segment;
pub mod service;
pub mod telemetry;
pub mod ipc;

use serde::{Deserialize, Serialize};

/// Engine profile — mirrors `RecordingEngineProfile` in contracts/recordingEngine.ts
/// and `RecordingProfile` in the Python domain.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EngineProfile {
    pub resolution: (u32, u32),
    pub fps: u32,
    pub codec: String,
    pub segment_minutes: u32,
    pub audio_enabled: bool, // locked false in P0-P1 (Principle F)
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

impl EngineProfile {
    /// Validate against the frozen contract — audio must stay false, fps 30|60,
    /// resolution in allowlist, segment 5|10.
    pub fn validate(&self) -> Result<(), String> {
        if self.audio_enabled {
            return Err("ENGINE_PROFILE_REJECTED: audio_enabled must be false (Principle F)".into());
        }
        if self.fps != 30 && self.fps != 60 {
            return Err(format!("ENGINE_PROFILE_REJECTED: fps must be 30 or 60, got {}", self.fps));
        }
        if self.resolution != (1920, 1080) && self.resolution != (1280, 720) && self.resolution != (3840, 2160) {
            return Err(format!("ENGINE_PROFILE_REJECTED: unsupported resolution {:?}", self.resolution));
        }
        if self.segment_minutes != 5 && self.segment_minutes != 10 {
            return Err(format!(
                "ENGINE_PROFILE_REJECTED: segment_minutes must be 5 or 10, got {}",
                self.segment_minutes
            ));
        }
        if self.codec != "H264" && self.codec != "HEVC" {
            return Err(format!("ENGINE_PROFILE_REJECTED: codec must be H264 or HEVC, got {}", self.codec));
        }
        Ok(())
    }
}

/// Segment manifest — tokenized, mirrors `SegmentManifest` in contracts/recordingEngine.ts
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SegmentManifest {
    pub take_id: String,
    pub execution_plan_id: String,
    pub segments: Vec<SegmentEntry>,
    pub timeline_ref: String, // timeline.jsonl token
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SegmentEntry {
    pub index: u32,
    pub file_token: String,
    pub duration_sec: f64,
    pub is_playable: bool,
}

/// Recording engine façade — ties capture → encode → mux → segment.
/// In production the engine runs as a sidecar process; here we expose the
/// interface so Tauri (control plane) and tests can drive it without IPC.
pub struct RecordingEngine {
    pub profile: EngineProfile,
    pub capture: Box<dyn capture::CapturePort>,
    pub encoder: Box<dyn encoder::EncoderPort>,
    pub muxer: Box<dyn muxer::MuxerPort>,
    pub segmenter: segment::Segmenter,
    pub preview: preview::PreviewSampler,
    pub telemetry: telemetry::Telemetry,
}

impl RecordingEngine {
    pub fn new_mock(profile: EngineProfile) -> Result<Self, String> {
        profile.validate()?;
        Ok(Self {
            profile: profile.clone(),
            capture: Box::new(capture::MockCapture::new(profile.resolution, profile.fps)),
            encoder: Box::new(encoder::MockEncoder::new(profile.codec.clone())),
            muxer: Box::new(muxer::MockMuxer::new()),
            segmenter: segment::Segmenter::new(profile.segment_minutes),
            preview: preview::PreviewSampler::new(preview::PreviewConfig {
                downscale: (1280, 720),
                fps: 1,
                format: preview::PreviewFormat::Jpeg,
            }),
            telemetry: telemetry::Telemetry::default(),
        })
    }

    /// Prepare validates profile and probes capabilities (fail-closed).
    pub fn prepare(&mut self, output_dir: &str) -> Result<(), String> {
        if output_dir.is_empty() {
            return Err("ENGINE_PREPARE_REJECTED: output_dir required".into());
        }
        self.profile.validate()?;
        self.capture.prepare()?;
        self.encoder.prepare()?;
        self.muxer.prepare(output_dir)?;
        Ok(())
    }
}
