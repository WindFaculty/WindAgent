//! IPC between Tauri (control plane) and Recording Engine (data plane)
//! Gate: LIVE_RECORD_V2_CONTRACT_FROZEN (ban_ke_hoach_v1.md §16)
//!
//! One JSON value per line on the sidecar's stdin/stdout:
//!   stdin  → `{"op":"capabilities"|"prepare"|…,"args":{…}}` ([EngineRequest])
//!   stdout → `{"resp":"ok"|"err",…}` per request, then `{"type":…}` events.
//!
//! Raw frames never travel this channel — only preview JPEGs (≤2 FPS),
//! audio meters, metrics and control state.

use serde::{Deserialize, Serialize};

/// Control-plane → data-plane requests.
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

/// Mute toggles reach the recorder itself (§11) — meters-only mute is forbidden.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MuteRequest {
    pub mic_muted: bool,
    pub system_muted: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "op", content = "args", rename_all = "snake_case")]
pub enum EngineRequest {
    Capabilities,
    /// §17 source picker data: enumerable monitors + top-level windows.
    /// Read-only — valid in every service state.
    Sources,
    Prepare(PrepareRequest),
    Start(StartRequest),
    Pause,
    Resume,
    Stop,
    Status,
    Marker(MarkerRequest),
    Mute(MuteRequest),
    /// Scan for an interrupted take, validate completed segments, rebuild the
    /// manifest, drop only the unfinished tail. (ban_ke_hoach_v1.md §15)
    Recover { output_dir: String },
}

impl EngineRequest {
    pub fn op_name(&self) -> &'static str {
        match self {
            Self::Capabilities => "capabilities",
            Self::Sources => "sources",
            Self::Prepare(_) => "prepare",
            Self::Start(_) => "start",
            Self::Pause => "pause",
            Self::Resume => "resume",
            Self::Stop => "stop",
            Self::Status => "status",
            Self::Marker(_) => "marker",
            Self::Mute(_) => "mute",
            Self::Recover { .. } => "recover",
        }
    }
}

/// Data-plane → control-plane response envelope — exactly one per request.
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
        Self::Ok { op: op.to_string(), payload }
    }

    pub fn err(op: &str, code: impl Into<String>, message: impl Into<String>) -> Self {
        Self::Err { op: op.to_string(), code: code.into(), message: message.into() }
    }
}

/// Real capability probe result — V2 native stack (fail-closed: every missing
/// piece adds a blocker and `engine_available=false`).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct EngineCapabilities {
    /// True only when D3D11 + WGC + NVENC (+ requested audio paths) all pass.
    pub engine_available: bool,
    /// "wgc-nvenc-mkv" in production; "mock" under explicit dev simulation.
    pub backend: String,
    pub contract_version: u32,

    // D3D11 device layer (§6)
    pub d3d11_ready: bool,
    pub gpu_adapter_name: String,
    pub gpu_vendor_id: u32,
    pub gpu_vram_mb: u64,
    pub d3d_feature_level: u32,
    pub nvidia_adapter_selected: bool,

    // WGC (§7)
    pub wgc_available: bool,
    pub wgc_os_supported: bool,

    // NVENC (§8)
    pub nvenc_available: bool,
    pub nvenc_api_version: u32,
    pub nvenc_h264_supported: bool,
    pub nvenc_hevc_supported: bool,
    pub nvenc_max_width: u32,
    pub nvenc_max_height: u32,
    pub nvenc_max_sessions: u32,
    pub nvenc_bframes_supported: bool,
    pub nvenc_lookahead_supported: bool,
    pub nvenc_aq_supported: bool,

    // Audio (§10/§11)
    pub wasapi_available: bool,
    pub mic_available: bool,
    pub system_loopback_available: bool,
    pub aac_encoder_available: bool,

    // Host
    pub disk_free_gb: f64,
    pub output_writable: bool,
    pub libav_runtime_found: bool,

    pub blockers: Vec<String>,
}

impl EngineCapabilities {
    pub fn has_blockers(&self) -> bool {
        !self.blockers.is_empty()
    }
}

// ─── Events ─────────────────────────────────────────────────────────────────

/// Rich telemetry snapshot — every field is measured, none is fabricated
/// (§17: "no fake recording metrics"). Optional fields are omitted from JSON
/// when their source probe is unavailable on the host.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TelemetrySnapshot {
    pub state: String,
    pub elapsed_sec: f64,
    pub take_id: String,
    pub current_segment_index: u32,

    // Capture / encode pipeline
    pub capture_fps: f64,
    pub encode_fps: f64,
    pub frames_captured: u64,
    pub frames_submitted: u64,
    pub frames_encoded: u64,
    pub frames_dropped: u64,
    pub dropped_pct: f64,
    pub capture_queue_depth: usize,
    pub encoder_queue_depth: usize,
    pub bitrate_mbps: f64,

    // NVENC latency + utilization (NVML-backed where available)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nvenc_latency_ms_p50: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nvenc_latency_ms_p95: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nvenc_util_pct: Option<f64>,

    // Host resources
    #[serde(skip_serializing_if = "Option::is_none")]
    pub gpu_util_pct: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub vram_used_mb: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cpu_util_pct: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ram_used_mb: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub gpu_temp_c: Option<f64>,

    // Disk
    pub disk_write_mbps: f64,
    pub disk_free_gb: f64,

    // A/V sync (QPC authority, §12)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub av_sync_error_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mic_drift_ppm: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub system_drift_ppm: Option<f64>,

    // Preview / director
    #[serde(skip_serializing_if = "Option::is_none")]
    pub preview_delay_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub director_latency_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub director_reconnects: Option<u32>,

    // Audio levels
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mic_rms_dbfs: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mic_peak_dbfs: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub system_rms_dbfs: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub system_peak_dbfs: Option<f64>,
    pub audio_underruns: u64,

    // Thermal/resource policy stage (§18): normal | preview_degraded | director_degraded | danger
    pub resource_stage: String,

    #[serde(skip_serializing_if = "Option::is_none")]
    pub nvenc_status: Option<String>,
}

/// Data-plane → control-plane events.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum EngineEvent {
    Status {
        #[serde(flatten)]
        telemetry: TelemetrySnapshot,
    },
    Segment {
        take_id: String,
        segment_index: u32,
        file_token: String,
        byte_len: u64,
        duration_sec: f64,
        is_playable: bool,
    },
    /// Down-scaled JPEG preview (≤1280×720, ≤2 FPS) — the only frame payload
    /// that ever crosses IPC.
    Preview {
        take_id: String,
        width: u32,
        height: u32,
        data_len: usize,
        timestamp_ms: u64,
        jpeg_base64: String,
    },
    /// Per-track loudness for UI meters (post-recorder-tap).
    AudioMeter {
        track: String,
        rms_dbfs: f64,
        peak_dbfs: f64,
        muted: bool,
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

/// Channel abstraction — production uses OS pipe / Tauri event emitter.
pub trait IpcChannel: Send {
    fn send(&mut self, event: EngineEvent) -> Result<(), String>;
}

#[derive(Default)]
pub struct VecChannel {
    pub events: Vec<EngineEvent>,
}

impl VecChannel {
    pub fn new() -> Self {
        Self { events: vec![] }
    }
}

impl IpcChannel for VecChannel {
    fn send(&mut self, event: EngineEvent) -> Result<(), String> {
        self.events.push(event);
        Ok(())
    }
}
