//! IPC contract types — mirrors `frontend/app/src/features/live-record/contracts/ipc.ts`.
//! V2 Native Cutover — Gate: LIVE_RECORD_V2_CONTRACT_FROZEN.
//!
//! Field names stay snake_case on both sides; Tauri receives the whole payload
//! as a single `request` struct so serde deserializes it 1:1 against the TS
//! interface. The nested `profile` mirrors `RecordingEngineProfile` from
//! `contracts/recordingEngine.ts` and is forwarded verbatim to the engine
//! sidecar — the control plane never re-interprets encoder settings (Principle D).

use serde::{Deserialize, Serialize};

use super::state::LiveRecordState;

/// Mirrors `RecorderStatus` in `contracts/ipc.ts`. Telemetry counters stay at
/// zero until the native engine reports real values.
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

    // §17 real telemetry — measured by the engine, merged in `merged_status`.
    pub capture_fps: f32,
    pub encode_fps: f32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub av_sync_error_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mic_drift_ppm: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub system_drift_ppm: Option<f64>,
    /// Resource stage (§18): normal | preview_degraded | director_degraded | danger
    pub resource_stage: String,

    pub current_segment_index: Option<u32>,
    pub current_segment_path: Option<String>,
    pub disk_write_mbps: Option<f32>,
    pub nvenc_status: String,
    pub bitrate_mbps: f32,
    pub preview_available: bool,
    pub blockers: Option<Vec<String>>,
}

/// Capability probe for preflight — mirrors `NativeCapabilities` in `contracts/ipc.ts`.
/// V2: every field comes from one real `capabilities` round-trip against the
/// native engine (`EngineCapabilities`); no ffmpeg/ddagrab remapping remains.
#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct NativeCapabilities {
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
    pub nvenc_bframes_supported: bool,
    pub nvenc_lookahead_supported: bool,
    pub nvenc_aq_supported: bool,

    // Audio (§10/§11) — multi-track, never mixed pre-record
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

// ─── Request payloads — mirror the TS request interfaces ─────────────────────

/// Mirrors `RecorderPrepareRequest` in `contracts/ipc.ts`.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct RecorderPrepareRequest {
    pub execution_plan_id: String,
    pub execution_plan_hash: String,
    pub episode_id: String,
    /// Validated server-side; never echoed back to the UI beyond a token.
    #[allow(dead_code)]
    pub output_dir: String,
    pub profile: RecorderProfile,
}

// ─── Profile V2 — mirrors `RecordingEngineProfile` ───────────────────────────

/// Mirrors `CaptureSource` in `contracts/recordingEngine.ts`.
#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct CaptureSource {
    pub kind: String, // "DISPLAY" | "WINDOW"
    pub id: String,
}

/// Mirrors `VideoConfig`. NVENC-only — validated fail-closed by the engine.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct VideoConfig {
    pub width: u32,
    pub height: u32,
    pub fps: u32,
    pub encoder: String,      // "NVENC" only
    pub codec: String,        // "H264" | "HEVC"
    pub rate_control: String, // "CQP"
    pub cq: i32,
    pub preset: String,       // P5|P6|P7
    pub multipass: String,    // DISABLED|HALF_RES|FULL_RES
    #[serde(default)]
    pub lookahead: u32,
    #[serde(default)]
    pub spatial_aq: bool,
    #[serde(default)]
    pub temporal_aq: bool,
    #[serde(default)]
    pub b_frames: u32,
    pub gop_frames: u32,
}

/// Mirrors `AudioTrackConfig`.
#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct AudioTrackConfig {
    pub enabled: bool,
    pub device_id: String,
}

/// Mirrors `AudioConfig` — mic and system become separate MKV tracks.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct AudioConfig {
    #[serde(default)]
    pub microphone: AudioTrackConfig,
    #[serde(default)]
    pub system: AudioTrackConfig,
    pub sample_rate: u32,
    pub codec: String, // "AAC"
}

/// Mirrors `ContainerConfig` — MKV master, segmented; MP4 is export-only.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ContainerConfig {
    pub format: String, // "MKV"
    pub segment_minutes: u32,
}

/// Mirrors the nested `profile` object of `RecorderPrepareRequest` (V2).
/// The sidecar's own validator is the single source of truth for every field;
/// this struct only carries the payload across IPC.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct RecorderProfile {
    #[serde(default)]
    pub capture_source: CaptureSource,
    pub video: VideoConfig,
    pub audio: AudioConfig,
    pub container: ContainerConfig,
}

impl Default for RecorderProfile {
    fn default() -> Self {
        // Quality-first defaults (ban_ke_hoach_v1.md §4) — mirrors
        // DEFAULT_ENGINE_PROFILE in contracts/recordingEngine.ts.
        Self {
            capture_source: CaptureSource { kind: "DISPLAY".into(), id: String::new() },
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
                // Mirrors the engine default: lookahead off — with no
                // B-frames it only delays packets (§15 crash window) and
                // starves sparse idle-screen frame delivery.
                lookahead: 0,
                spatial_aq: true,
                temporal_aq: true,
                // Mirrors the engine default: B-frames off — sync mode with a
                // single output bitstream buffer returns pictures in
                // completion (presentation) order once a B-chain forms,
                // which Matroska's decode-order requirement forbids.
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

/// Mirrors `RecorderStartRequest` in `contracts/ipc.ts`.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct RecorderStartRequest {
    pub execution_plan_id: String,
    pub take_id: Option<String>,
}

/// Mirrors `MarkerRequest` in `contracts/ipc.ts`.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct MarkerRequest {
    pub marker_type: String,
    pub cue_id: Option<String>,
    pub action_id: Option<String>,
}

/// Mirrors `MuteRequest` (V2) — toggles reach the recorder itself (§11);
/// meters-only mute is forbidden.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct MuteRequest {
    pub mic_muted: bool,
    pub system_muted: bool,
}

/// Mirrors the recover op args (§15 crash-safe recovery).
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct RecoverRequest {
    /// Tokenized or absolute output root previously prepared for a take set.
    pub output_dir: String,
}

// ─── Source picker (§17) — mirrors `CaptureSources` in `contracts/ipc.ts` ────

/// One enumerable display target (`CaptureSourceKind = "DISPLAY"`).
#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct MonitorSource {
    pub kind: String, // "DISPLAY"
    /// Device path fed back verbatim as `capture_source.id`.
    pub id: String,
    pub label: String,
    #[serde(default)]
    pub width: u32,
    #[serde(default)]
    pub height: u32,
    #[serde(default)]
    pub is_primary: bool,
}

/// One enumerable window target (`CaptureSourceKind = "WINDOW"`).
#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct WindowSource {
    pub kind: String, // "WINDOW"
    /// HWND token fed back verbatim as `capture_source.id`.
    pub id: String,
    pub label: String,
    #[serde(default)]
    pub process: String,
}

/// Payload of `recorder_get_sources` — real WGC enumeration from the engine.
#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct CaptureSources {
    #[serde(default)]
    pub monitors: Vec<MonitorSource>,
    #[serde(default)]
    pub windows: Vec<WindowSource>,
}
