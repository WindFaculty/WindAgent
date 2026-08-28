//! WindAgent Recording Engine — Data Plane (V2 native cutover)
//! Gate: LIVE_RECORD_V2_CONTRACT_FROZEN
//!
//! This crate is the **data plane**. Tauri (`apps/desktop/src-tauri`) is the
//! **control plane** — it never touches NVENC/libav directly; it only sends
//! requests over JSONL stdin and receives events on stdout.
//!
//! Production pipeline (ban_ke_hoach_v1.md §1, §3):
//! ```text
//! Windows Graphics Capture (WGC)
//!           │  (GPU texture, never copied to CPU in the hot path)
//!           ▼
//!     ID3D11Texture2D ─────────────► GPU preview path (downscale ≤1280×720,
//!           │                          JPEG, ≤2 FPS — CPU readback allowed here)
//!           ▼
//!   NVENC direct (registered D3D11 resource, zero-copy)
//!           │
//!           ▼
//!      Encoded H264/HEVC ──┬── Mic WASAPI track
//!                          ├── System WASAPI loopback track
//!                          ▼
//!                    libavformat (MKV)
//!                          ▼
//!              segmented MKV + timeline.jsonl + manifest.json
//! ```
//!
//! Hard principles (§3): zero-copy hot path · FFmpeg CLI is not a production
//! capture backend · NVENC fail-closed (no x264 fallback) · MKV master ·
//! multi-track audio · QPC single clock authority · recording > AI priority ·
//! native status is source of truth.

pub mod audio;
pub mod capture;
pub mod clock;
pub mod encoder;
pub mod ipc;
pub mod muxer;
pub mod pipeline;
pub mod preview;
pub mod probe;
pub mod segment;
pub mod service;
pub mod telemetry;

use serde::{Deserialize, Serialize};

/// Wire-contract version bumped on every breaking profile change.
/// Mirrors `ENGINE_CONTRACT_VERSION` in contracts/recordingEngine.ts.
pub const ENGINE_CONTRACT_VERSION: u32 = 2;

// ─── Capture source ──────────────────────────────────────────────────────────

/// Mirrors `CaptureSource` in contracts/recordingEngine.ts.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CaptureSource {
    pub kind: CaptureSourceKind,
    /// Monitor device path (DISPLAY) or window token (WINDOW); empty = primary display.
    pub id: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum CaptureSourceKind {
    Display,
    Window,
}

// ─── Video config ────────────────────────────────────────────────────────────

/// Mirrors `VideoConfig` in contracts/recordingEngine.ts.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VideoConfig {
    pub width: u32,
    pub height: u32,
    pub fps: u32,

    pub encoder: String, // "NVENC" only — validated fail-closed
    pub codec: String,   // "H264" | "HEVC"

    pub rate_control: String, // "CQP" only in V2
    pub cq: i32,

    pub preset: String,    // "P5" | "P6" | "P7"
    pub multipass: String, // "DISABLED" | "HALF_RES" | "FULL_RES"
    pub lookahead: u32,
    pub spatial_aq: bool,
    pub temporal_aq: bool,
    pub b_frames: u32,
    pub gop_frames: u32,
}

// ─── Audio config (multi-track) ──────────────────────────────────────────────

/// Mirrors `AudioTrackConfig`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AudioTrackConfig {
    pub enabled: bool,
    /// WASAPI endpoint id; empty = default device.
    pub device_id: String,
}

/// Mirrors `AudioConfig`. Mic and system are separate MKV tracks — never mixed.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AudioConfig {
    pub microphone: AudioTrackConfig,
    pub system: AudioTrackConfig,
    pub sample_rate: u32,
    pub codec: String, // "AAC"
}

// ─── Container ───────────────────────────────────────────────────────────────

/// Mirrors `ContainerConfig`. MKV is the master container; MP4 is export-only.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ContainerConfig {
    pub format: String, // "MKV" only
    pub segment_minutes: u32,
}

// ─── Profile V2 ──────────────────────────────────────────────────────────────

/// Engine profile V2 — mirrors `RecordingEngineProfile` in contracts/recordingEngine.ts.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EngineProfile {
    pub capture_source: CaptureSource,
    pub video: VideoConfig,
    pub audio: AudioConfig,
    pub container: ContainerConfig,
}

impl Default for EngineProfile {
    fn default() -> Self {
        // Default quality-first profile (ban_ke_hoach_v1.md §4).
        Self {
            capture_source: CaptureSource {
                kind: CaptureSourceKind::Display,
                id: String::new(),
            },
            video: VideoConfig {
                width: 1920,
                height: 1080,
                fps: 60,
                encoder: "NVENC".into(),
                codec: "H264".into(),
                rate_control: "CQP".into(),
                cq: 16,
                preset: "P7".into(),
                multipass: "FULL_RES".into(),
                // Lookahead stays off by default: with no B-frames (below) it
                // buys only rate smoothing while holding up to `depth`
                // frames unflushed — a crash-loss window against §15
                // crash-safe segments, and on idle screens (WGC delivers
                // frames sparsely) the take can end before the pipeline
                // ever drains. Explicit profiles may still opt in ≤ 32.
                lookahead: 0,
                spatial_aq: true,
                temporal_aq: true,
                // B-frames stay off by default: the session runs NVENC sync
                // mode with a single output bitstream buffer, and a B-chain
                // completes pictures in presentation order — muxing that
                // stream violates Matroska's decode-order requirement
                // (missing-reference cascade on playback). Screen content
                // compresses nearly as well with P-frames alone.
                b_frames: 0,
                gop_frames: 120,
            },
            audio: AudioConfig {
                microphone: AudioTrackConfig { enabled: true, device_id: String::new() },
                system: AudioTrackConfig { enabled: true, device_id: String::new() },
                sample_rate: 48000,
                codec: "AAC".into(),
            },
            container: ContainerConfig { format: "MKV".into(), segment_minutes: 5 },
        }
    }
}

impl EngineProfile {
    /// Validate against the frozen V2 contract. Every violation names its field.
    pub fn validate(&self) -> Result<(), String> {
        let v = &self.video;
        if v.encoder != "NVENC" {
            return Err(format!(
                "ENGINE_PROFILE_REJECTED: video.encoder must be NVENC (no software fallback), got {}",
                v.encoder
            ));
        }
        if v.codec != "H264" && v.codec != "HEVC" {
            return Err(format!("ENGINE_PROFILE_REJECTED: video.codec must be H264 or HEVC, got {}", v.codec));
        }
        if self.capture_source.kind != CaptureSourceKind::Display
            && self.capture_source.kind != CaptureSourceKind::Window
        {
            return Err("ENGINE_PROFILE_REJECTED: capture_source.kind must be DISPLAY or WINDOW".into());
        }
        if v.fps != 30 && v.fps != 60 {
            return Err(format!("ENGINE_PROFILE_REJECTED: video.fps must be 30 or 60, got {}", v.fps));
        }
        let resolution = (v.width, v.height);
        if resolution != (1920, 1080) && resolution != (1280, 720) && resolution != (3840, 2160) {
            return Err(format!("ENGINE_PROFILE_REJECTED: unsupported resolution {:?}", resolution));
        }
        if v.rate_control != "CQP" {
            return Err(format!("ENGINE_PROFILE_REJECTED: video.rate_control must be CQP, got {}", v.rate_control));
        }
        if !(10..=30).contains(&v.cq) {
            return Err(format!("ENGINE_PROFILE_REJECTED: video.cq out of range [10,30], got {}", v.cq));
        }
        if !matches!(v.preset.as_str(), "P5" | "P6" | "P7") {
            return Err(format!("ENGINE_PROFILE_REJECTED: video.preset must be P5|P6|P7, got {}", v.preset));
        }
        if !matches!(v.multipass.as_str(), "DISABLED" | "HALF_RES" | "FULL_RES") {
            return Err(format!("ENGINE_PROFILE_REJECTED: video.multipass invalid, got {}", v.multipass));
        }
        if v.lookahead > 32 {
            return Err(format!("ENGINE_PROFILE_REJECTED: video.lookahead max 32, got {}", v.lookahead));
        }
        if v.b_frames > 4 {
            return Err(format!("ENGINE_PROFILE_REJECTED: video.b_frames max 4, got {}", v.b_frames));
        }
        if v.gop_frames == 0 || v.gop_frames > v.fps * 10 {
            return Err(format!(
                "ENGINE_PROFILE_REJECTED: video.gop_frames must be in [1, {}], got {}",
                v.fps * 10,
                v.gop_frames
            ));
        }
        if self.audio.sample_rate != 48000 {
            return Err(format!("ENGINE_PROFILE_REJECTED: audio.sample_rate must be 48000, got {}", self.audio.sample_rate));
        }
        if self.audio.codec != "AAC" {
            return Err(format!("ENGINE_PROFILE_REJECTED: audio.codec must be AAC, got {}", self.audio.codec));
        }
        if self.container.format != "MKV" {
            return Err(format!("ENGINE_PROFILE_REJECTED: container.format must be MKV, got {}", self.container.format));
        }
        if self.container.segment_minutes != 5 && self.container.segment_minutes != 10 {
            return Err(format!(
                "ENGINE_PROFILE_REJECTED: container.segment_minutes must be 5 or 10, got {}",
                self.container.segment_minutes
            ));
        }
        Ok(())
    }
}

// ─── Segment manifest ────────────────────────────────────────────────────────

/// Segment manifest — mirrors `SegmentManifest` in contracts/recordingEngine.ts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SegmentManifest {
    pub take_id: String,
    pub execution_plan_id: String,
    pub segments: Vec<SegmentEntry>,
    pub timeline_ref: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SegmentEntry {
    pub index: u32,
    pub file_token: String,
    pub duration_sec: f64,
    pub byte_len: u64,
    pub is_playable: bool,
}
