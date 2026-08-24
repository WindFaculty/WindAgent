//! IPC between Tauri (control plane) and Recording Engine (data plane)
//! (ban_ke_hoach_v1.md Section 19)
//!
//! Tauri commands (small surface):
//!   recorder_prepare / start / pause / resume / stop / get_status / create_marker
//! Events:
//!   recorder://status / segment / preview / warning / error / timeline
//!
//! The engine runs as a sidecar process in production; in tests the Engine is
//! driven in-process via `RecordingEngine::new_mock` without spawning a process.

use serde::{Deserialize, Serialize};

/// Control-plane → data-plane requests (mirrors Tauri `RecorderPrepareRequest` etc.)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PrepareRequest {
    pub execution_plan_id: String,
    pub execution_plan_hash: String,
    pub episode_id: String,
    pub output_dir: String,
    pub profile: crate::EngineProfile,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StartRequest {
    pub execution_plan_id: String,
    pub take_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarkerRequest {
    pub marker_type: String,
    pub cue_id: Option<String>,
    pub action_id: Option<String>,
}

/// Data-plane → control-plane events (mirrors `RecorderEventName` in contracts/ipc.ts)
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum EngineEvent {
    Status {
        state: String,
        elapsed_sec: f64,
        frames_captured: u64,
        frames_encoded: u64,
        frames_dropped: u64,
        dropped_pct: f64,
        bitrate_mbps: f64,
        #[serde(skip_serializing_if = "Option::is_none")]
        nvenc_status: Option<String>,
    },
    Segment {
        take_id: String,
        segment_index: u32,
        file_token: String,
        is_playable: bool,
    },
    /// Down-scaled JPEG preview (≤1280×720, ≤2 FPS) — the only frame payload
    /// that ever crosses IPC (Principle E). `jpeg_base64` carries the actual
    /// bytes for the Gemini FrameSampler; mock mode leaves it empty.
    Preview {
        take_id: String,
        width: u32,
        height: u32,
        data_len: usize,
        timestamp_ms: u64,
        #[serde(default)]
        jpeg_base64: String,
    },
    Warning {
        message: String,
    },
    Error {
        message: String,
    },
    Timeline {
        take_id: String,
        event_type: String,
        t: f64,
    },
}

/// Control-plane → data-plane request envelope — one JSON line on the
/// sidecar's stdin. Mirrors the 8-command Tauri surface 1:1.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "op", content = "args", rename_all = "snake_case")]
pub enum EngineRequest {
    Capabilities,
    Prepare(PrepareRequest),
    Start(StartRequest),
    Pause,
    Resume,
    Stop,
    Status,
    Marker(MarkerRequest),
}

impl EngineRequest {
    pub fn op_name(&self) -> &'static str {
        match self {
            Self::Capabilities => "capabilities",
            Self::Prepare(_) => "prepare",
            Self::Start(_) => "start",
            Self::Pause => "pause",
            Self::Resume => "resume",
            Self::Stop => "stop",
            Self::Status => "status",
            Self::Marker(_) => "marker",
        }
    }
}

/// Data-plane → control-plane response envelope — exactly one per request,
/// emitted before any events that the request triggers.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "resp", rename_all = "snake_case")]
pub enum EngineResponse {
    Ok {
        op: String,
        payload: serde_json::Value,
    },
    Err {
        op: String,
        code: String,
        message: String,
    },
}

impl EngineResponse {
    pub fn ok(op: &str, payload: serde_json::Value) -> Self {
        Self::Ok {
            op: op.to_string(),
            payload,
        }
    }

    pub fn err(op: &str, code: impl Into<String>, message: impl Into<String>) -> Self {
        Self::Err {
            op: op.to_string(),
            code: code.into(),
            message: message.into(),
        }
    }
}

/// Real capability probe result (fail-closed: every false adds a blocker).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct EngineCapabilities {
    pub engine_available: bool,
    /// "ffmpeg-ddagrab-nvenc" (real pipeline) or "mock" (dev/CI simulation).
    pub backend: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ffmpeg_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ffmpeg_version: Option<String>,
    pub ddagrab_available: bool,
    pub nvenc_h264_available: bool,
    pub nvenc_hevc_available: bool,
    pub disk_free_gb: f64,
    pub output_writable: bool,
    pub blockers: Vec<String>,
}

/// Channel abstraction — production uses OS pipe / Tauri event emitter.
pub trait IpcChannel: Send {
    fn send(&mut self, event: EngineEvent) -> Result<(), String>;
}

pub struct NoopChannel;

impl IpcChannel for NoopChannel {
    fn send(&mut self, _event: EngineEvent) -> Result<(), String> {
        Ok(())
    }
}

pub struct VecChannel {
    pub events: Vec<EngineEvent>,
}

impl VecChannel {
    pub fn new() -> Self {
        Self { events: vec![] }
    }
}

impl Default for VecChannel {
    fn default() -> Self {
        Self::new()
    }
}

impl IpcChannel for VecChannel {
    fn send(&mut self, event: EngineEvent) -> Result<(), String> {
        self.events.push(event);
        Ok(())
    }
}
