//! Recorder control-plane commands — Phase 8/9 wiring over the Phase 0 core.
//! Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN
//!
//! The plain `*_core` functions below are the pure state-machine logic the
//! gate tests exercise; the Tauri commands layer them with the real engine:
//!
//! - sidecar present → every command is forwarded over the frozen JSONL
//!   protocol and the control plane reflects what the data plane reports,
//! - no sidecar (web dev / CI) → the exact Phase 0 fail-closed behaviour
//!   (preflight lands in BLOCKED, start can never succeed).
//!
//! Capture/encode/mux work never happens here (Principle D).

use std::sync::{Arc, Mutex};

use serde_json::{json, Value};
use tauri::{AppHandle, State};

use super::engine_host::{EngineHost, EngineHostState};
use super::state::{assert_transition, can_transition, LiveRecordState, RecorderSharedState};
use super::types::{
    MarkerRequest, NativeCapabilities, RecorderPrepareRequest, RecorderStartRequest,
    RecorderStatus,
};

// ─── Core logic (pure over shared state — unit-testable) ─────────────────────

fn is_sha256_hex(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit())
}

/// Validate a prepare payload without touching state — shared by both paths.
pub(crate) fn validate_prepare_request(
    request: &RecorderPrepareRequest,
) -> Result<(), String> {
    if request.execution_plan_id.is_empty() || request.episode_id.is_empty() {
        return Err("RECORDER_PREPARE_REJECTED: missing execution_plan_id/episode_id".into());
    }
    if !is_sha256_hex(&request.execution_plan_hash) {
        return Err("RECORDER_PREPARE_REJECTED: plan_hash must be sha256 hex".into());
    }
    if request.profile.audio_enabled {
        // Principle F — audio stays disabled until the TTS stage.
        return Err("RECORDER_PREPARE_REJECTED: audio_enabled must be false in P0".into());
    }
    Ok(())
}

/// IDLE/BLOCKED/FAILED → PREPARING → PREFLIGHT → BLOCKED (no-engine path).
pub(crate) fn prepare_core(
    shared: &mut RecorderSharedState,
    request: &RecorderPrepareRequest,
) -> Result<String, String> {
    validate_prepare_request(request)?;

    assert_transition(shared.state, LiveRecordState::Preparing)?;
    shared.execution_plan_id = Some(request.execution_plan_id.clone());
    shared.execution_plan_hash = Some(request.execution_plan_hash.clone());
    shared.blockers.clear();
    shared.state = LiveRecordState::Preparing;

    assert_transition(shared.state, LiveRecordState::Preflight)?;
    shared.state = LiveRecordState::Preflight;

    // No engine sidecar: capture probes are unavailable → fail closed.
    shared.blockers = vec![
        "WGC_UNAVAILABLE".into(),
        "NVENC_UNAVAILABLE".into(),
    ];
    assert_transition(shared.state, LiveRecordState::Blocked)?;
    shared.state = LiveRecordState::Blocked;

    Ok(format!("PREPARED:{}", request.execution_plan_id))
}

/// Only READY may transition to RECORDING (fail-closed; BLOCKED cannot start).
pub(crate) fn start_core(
    shared: &mut RecorderSharedState,
    request: &RecorderStartRequest,
) -> Result<String, String> {
    if let Some(plan_id) = shared.execution_plan_id.as_deref() {
        if plan_id != request.execution_plan_id {
            return Err("RECORDER_PLAN_MISMATCH: execution_plan_id does not match prepared plan".into());
        }
    }
    assert_transition(shared.state, LiveRecordState::Recording).map_err(|_| {
        format!(
            "RECORDER_NOT_READY: cannot start from {} (plan BLOCKED or not prepared)",
            shared.state.as_str()
        )
    })?;

    let take_id = request.take_id.clone().unwrap_or_else(|| {
        let ts = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0);
        format!("take_{ts}")
    });
    shared.take_id = Some(take_id.clone());
    shared.state = LiveRecordState::Recording;
    Ok(take_id)
}

pub(crate) fn pause_core(shared: &mut RecorderSharedState) -> Result<(), String> {
    assert_transition(shared.state, LiveRecordState::Paused)?;
    shared.state = LiveRecordState::Paused;
    Ok(())
}

pub(crate) fn resume_core(shared: &mut RecorderSharedState) -> Result<(), String> {
    assert_transition(shared.state, LiveRecordState::Recording)?;
    shared.state = LiveRecordState::Recording;
    Ok(())
}

/// RECORDING|PAUSED → FINALIZING → COMPLETED.
pub(crate) fn stop_core(shared: &mut RecorderSharedState) -> Result<String, String> {
    if !can_transition(shared.state, LiveRecordState::Finalizing) {
        return Err(format!(
            "RECORDER_NOT_RECORDING: cannot stop from {}",
            shared.state.as_str()
        ));
    }
    shared.state = LiveRecordState::Finalizing;
    assert_transition(shared.state, LiveRecordState::Completed)?;
    shared.state = LiveRecordState::Completed;
    Ok(
        shared
            .take_id
            .clone()
            .unwrap_or_else(|| "take_unassigned".into()),
    )
}

/// Markers require RECORDING or PAUSED.
pub(crate) fn create_marker_core(
    shared: &RecorderSharedState,
    request: &MarkerRequest,
) -> Result<String, String> {
    if !matches!(
        shared.state,
        LiveRecordState::Recording | LiveRecordState::Paused
    ) {
        return Err(format!(
            "RECORDER_MARKER_REJECTED: markers require RECORDING/PAUSED, current {}",
            shared.state.as_str()
        ));
    }
    if request.marker_type.is_empty() {
        return Err("RECORDER_MARKER_REJECTED: marker_type is required".into());
    }
    Ok(format!("MARKER_ACK:{}", request.marker_type))
}

pub(crate) fn status_of(shared: &RecorderSharedState) -> RecorderStatus {
    RecorderStatus {
        state: shared.state,
        take_id: shared.take_id.clone(),
        execution_plan_id: shared.execution_plan_id.clone(),
        elapsed_sec: 0,
        frames_captured: 0,
        frames_encoded: 0,
        frames_dropped: 0,
        dropped_pct: 0.0,
        current_segment_index: None,
        current_segment_path: None,
        disk_write_mbps: None,
        nvenc_status: "IDLE".into(),
        bitrate_mbps: 0.0,
        preview_available: false,
        blockers: if shared.blockers.is_empty() {
            None
        } else {
            Some(shared.blockers.clone())
        },
    }
}

// ─── Engine-side helpers ─────────────────────────────────────────────────────

type EngineGuard<'a> = std::sync::MutexGuard<'a, Option<EngineHost>>;
type SharedGuard<'a> = std::sync::MutexGuard<'a, RecorderSharedState>;

/// Make sure a live host exists (spawning it on first use); the caller then
/// borrows it with `host_of`. Split in two so no borrow is held across the
/// spawn.
fn ensure_spawned(engine: &mut EngineGuard<'_>, app: &AppHandle) -> bool {
    let alive = matches!(engine.as_ref(), Some(host) if host.is_alive());
    if alive {
        return true;
    }
    let Some(sidecar) = EngineHost::locate_sidecar() else {
        return false;
    };
    let sink: Arc<dyn super::engine_host::EventSink> = Arc::new(app.clone());
    match EngineHost::spawn(sidecar, sink) {
        Ok(host) => {
            **engine = Some(host);
            true
        }
        Err(_) => false,
    }
}

/// Borrow the host after `ensure_spawned` returned true.
fn host_of<'a>(engine: &'a mut EngineGuard<'_>) -> &'a mut EngineHost {
    engine
        .as_mut()
        .expect("ensure_spawned must have installed the host")
}

/// Send one request and unwrap its `{"resp":"ok","payload":…}` envelope.
fn engine_ok(host: &mut EngineHost, request: Value, op: &str) -> Result<Value, String> {
    let response = host.request(&request)?;
    match response.get("resp").and_then(Value::as_str) {
        Some("ok") => Ok(response.get("payload").cloned().unwrap_or(Value::Null)),
        Some("err") => {
            let code = response
                .get("code")
                .and_then(Value::as_str)
                .unwrap_or("ENGINE_ERROR");
            let message = response
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("");
            Err(format!("{code}: {message}"))
        }
        _ => Err(format!("ENGINE_MALFORMED_RESPONSE for op '{op}'")),
    }
}

/// `"1920x1080"` (TS contract) → `[1920, 1080]` (sidecar tuple).
fn parse_resolution(spec: &str) -> Result<[u32; 2], String> {
    let (w, h) = spec
        .split_once(['x', 'X'])
        .ok_or_else(|| format!("RECORDER_PREPARE_REJECTED: bad resolution '{spec}'"))?;
    let width: u32 = w
        .trim()
        .parse()
        .map_err(|_| format!("RECORDER_PREPARE_REJECTED: bad resolution '{spec}'"))?;
    let height: u32 = h
        .trim()
        .parse()
        .map_err(|_| format!("RECORDER_PREPARE_REJECTED: bad resolution '{spec}'"))?;
    Ok([width, height])
}

/// Build the sidecar's `prepare` args from the TS-mirror request struct.
fn sidecar_prepare_args(request: &RecorderPrepareRequest) -> Value {
    let profile = &request.profile;
    let codec = if profile.codec.eq_ignore_ascii_case("hevc") {
        "HEVC"
    } else {
        "H264"
    };
    // Validation already ran; a bad spec falls back to the 1080p default so
    // the sidecar's own validator is the single source of truth.
    let resolution = parse_resolution(&profile.resolution).unwrap_or([1920, 1080]);
    json!({
        "op": "prepare",
        "args": {
            "execution_plan_id": request.execution_plan_id,
            "execution_plan_hash": request.execution_plan_hash,
            "episode_id": request.episode_id,
            "output_dir": request.output_dir,
            "profile": {
                "resolution": resolution,
                "fps": profile.fps,
                "codec": codec,
                "segment_minutes": profile.segment_minutes,
                "audio_enabled": profile.audio_enabled,
            },
        }
    })
}

fn sidecar_capabilities_to_native(payload: &Value) -> NativeCapabilities {
    NativeCapabilities {
        // ddagrab IS the desktop-capture capability in this backend.
        wgc_available: payload
            .get("ddagrab_available")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        nvenc_available: payload
            .get("nvenc_h264_available")
            .and_then(Value::as_bool)
            .or_else(|| payload.get("nvenc_hevc_available").and_then(Value::as_bool))
            .unwrap_or(false),
        wasapi_available: false, // Principle F: locked through P1
        disk_free_gb: payload
            .get("disk_free_gb")
            .and_then(Value::as_f64)
            .unwrap_or(0.0) as f32,
        output_writable: payload
            .get("output_writable")
            .and_then(Value::as_bool)
            .unwrap_or(false),
    }
}

fn probe_native_capabilities(host: &mut EngineHost) -> Result<NativeCapabilities, String> {
    let payload = engine_ok(host, json!({"op": "capabilities"}), "capabilities")?;
    Ok(sidecar_capabilities_to_native(&payload))
}

/// Merge live sidecar telemetry into the control-plane status view.
fn merged_status(shared: &RecorderSharedState, telemetry: &Value) -> RecorderStatus {
    let mut status = status_of(shared);
    status.elapsed_sec =
        telemetry.get("elapsed_sec").and_then(Value::as_f64).unwrap_or(0.0) as u64;
    status.frames_captured =
        telemetry.get("frames_captured").and_then(Value::as_u64).unwrap_or(0);
    status.frames_encoded =
        telemetry.get("frames_encoded").and_then(Value::as_u64).unwrap_or(0);
    status.frames_dropped =
        telemetry.get("frames_dropped").and_then(Value::as_u64).unwrap_or(0);
    status.dropped_pct =
        telemetry.get("dropped_pct").and_then(Value::as_f64).unwrap_or(0.0) as f32;
    status.bitrate_mbps =
        telemetry.get("bitrate_mbps").and_then(Value::as_f64).unwrap_or(0.0) as f32;
    if let Some(nvenc) = telemetry.get("nvenc_status").and_then(Value::as_str) {
        status.nvenc_status = nvenc.to_string();
    }
    if let Some(state) = telemetry.get("state").and_then(Value::as_str) {
        status.state = match state {
            "RECORDING" => LiveRecordState::Recording,
            "PAUSED" => LiveRecordState::Paused,
            "STOPPED" | "COMPLETED" => LiveRecordState::Completed,
            "IDLE" if shared.state == LiveRecordState::Idle => LiveRecordState::Idle,
            _ => shared.state,
        };
    }
    status.preview_available = status.nvenc_status == "ENCODING";
    status
}

// ─── Tauri commands ──────────────────────────────────────────────────────────

type SharedHandle<'a> = State<'a, Mutex<RecorderSharedState>>;
type EngineHandle<'a> = State<'a, EngineHostState>;

fn lock<'a>(
    shared: &'a SharedHandle<'_>,
) -> Result<SharedGuard<'a>, String> {
    shared.lock().map_err(|_| "RECORDER_STATE_POISONED".to_string())
}

fn lock_engine<'a>(engine: &'a EngineHandle<'_>) -> Result<EngineGuard<'a>, String> {
    engine.0.lock().map_err(|_| "ENGINE_STATE_POISONED".to_string())
}

#[tauri::command]
pub fn recorder_prepare(
    request: RecorderPrepareRequest,
    shared: SharedHandle<'_>,
    engine: EngineHandle<'_>,
    app: AppHandle,
) -> Result<String, String> {
    validate_prepare_request(&request)?;
    let mut shared_guard = lock(&shared)?;
    let mut engine_guard = lock_engine(&engine)?;

    if ensure_spawned(&mut engine_guard, &app) {
        let capabilities = probe_native_capabilities(host_of(&mut engine_guard))?;

        assert_transition(shared_guard.state, LiveRecordState::Preparing)?;
        shared_guard.blockers.clear();
        shared_guard.state = LiveRecordState::Preparing;

        assert_transition(shared_guard.state, LiveRecordState::Preflight)?;
        shared_guard.state = LiveRecordState::Preflight;

        if capabilities.wgc_available && capabilities.nvenc_available {
            let args = sidecar_prepare_args(&request);
            let payload = engine_ok(host_of(&mut engine_guard), args, "prepare")?;
            if payload.get("prepared").and_then(Value::as_bool) == Some(true) {
                assert_transition(shared_guard.state, LiveRecordState::Ready)?;
                shared_guard.state = LiveRecordState::Ready;
                return Ok(format!("READY:{}", request.execution_plan_id));
            }
            shared_guard.blockers = blockers_of(&payload, "ENGINE_PREPARE_FAILED");
            assert_transition(shared_guard.state, LiveRecordState::Blocked)?;
            shared_guard.state = LiveRecordState::Blocked;
            return Err("ENGINE_PREPARE_FAILED: sidecar rejected prepare".into());
        }

        // Real probe says this host cannot record — surface ITS blockers.
        let payload = engine_ok(
            host_of(&mut engine_guard),
            json!({"op": "capabilities"}),
            "capabilities",
        )?;
        shared_guard.blockers = blockers_of(&payload, "ENGINE_UNAVAILABLE");
        assert_transition(shared_guard.state, LiveRecordState::Blocked)?;
        shared_guard.state = LiveRecordState::Blocked;
        return Ok(format!("BLOCKED:{}", request.execution_plan_id));
    }

    prepare_core(&mut shared_guard, &request)
}

fn blockers_of(payload: &Value, fallback: &str) -> Vec<String> {
    payload["blockers"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .filter(|v: &Vec<String>| !v.is_empty())
        .unwrap_or_else(|| vec![fallback.to_string()])
}

#[tauri::command]
pub fn recorder_start(
    request: RecorderStartRequest,
    shared: SharedHandle<'_>,
    engine: EngineHandle<'_>,
    app: AppHandle,
) -> Result<String, String> {
    let mut shared_guard = lock(&shared)?;
    let mut engine_guard = lock_engine(&engine)?;
    if ensure_spawned(&mut engine_guard, &app) {
        let take_id = request.take_id.clone().unwrap_or_default();
        let payload = engine_ok(
            host_of(&mut engine_guard),
            json!({
                "op": "start",
                "args": {
                    "execution_plan_id": request.execution_plan_id,
                    "take_id": take_id,
                }
            }),
            "start",
        )?;
        let take_id = payload
            .get("take_id")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();

        assert_transition(shared_guard.state, LiveRecordState::Recording).map_err(|_| {
            format!(
                "RECORDER_NOT_READY: cannot start from {} (plan BLOCKED or not prepared)",
                shared_guard.state.as_str()
            )
        })?;
        shared_guard.take_id = Some(take_id.clone());
        shared_guard.state = LiveRecordState::Recording;
        return Ok(take_id);
    }

    start_core(&mut shared_guard, &request)
}

#[tauri::command]
pub fn recorder_pause(
    shared: SharedHandle<'_>,
    engine: EngineHandle<'_>,
    app: AppHandle,
) -> Result<(), String> {
    let mut shared_guard = lock(&shared)?;
    let mut engine_guard = lock_engine(&engine)?;
    if ensure_spawned(&mut engine_guard, &app) {
        engine_ok(host_of(&mut engine_guard), json!({"op": "pause"}), "pause")?;
    }
    pause_core(&mut shared_guard)
}

#[tauri::command]
pub fn recorder_resume(
    shared: SharedHandle<'_>,
    engine: EngineHandle<'_>,
    app: AppHandle,
) -> Result<(), String> {
    let mut shared_guard = lock(&shared)?;
    let mut engine_guard = lock_engine(&engine)?;
    if ensure_spawned(&mut engine_guard, &app) {
        engine_ok(host_of(&mut engine_guard), json!({"op": "resume"}), "resume")?;
    }
    resume_core(&mut shared_guard)
}

#[tauri::command]
pub fn recorder_stop(
    shared: SharedHandle<'_>,
    engine: EngineHandle<'_>,
    app: AppHandle,
) -> Result<String, String> {
    let mut shared_guard = lock(&shared)?;
    let mut engine_guard = lock_engine(&engine)?;
    if !can_transition(shared_guard.state, LiveRecordState::Finalizing) {
        return Err(format!(
            "RECORDER_NOT_RECORDING: cannot stop from {}",
            shared_guard.state.as_str()
        ));
    }
    if ensure_spawned(&mut engine_guard, &app) {
        let payload = engine_ok(host_of(&mut engine_guard), json!({"op": "stop"}), "stop")?;
        let take_id = payload
            .get("take_id")
            .and_then(Value::as_str)
            .unwrap_or("take_unassigned")
            .to_string();
        shared_guard.state = LiveRecordState::Finalizing;
        assert_transition(shared_guard.state, LiveRecordState::Completed)?;
        shared_guard.state = LiveRecordState::Completed;
        shared_guard.take_id = Some(take_id.clone());
        return Ok(take_id);
    }

    stop_core(&mut shared_guard)
}

#[tauri::command]
pub fn recorder_create_marker(
    request: MarkerRequest,
    shared: SharedHandle<'_>,
    engine: EngineHandle<'_>,
    app: AppHandle,
) -> Result<String, String> {
    create_marker_core(&*lock(&shared)?, &request)?; // same gating either way

    let mut engine_guard = lock_engine(&engine)?;
    if ensure_spawned(&mut engine_guard, &app) {
        engine_ok(
            host_of(&mut engine_guard),
            json!({
                "op": "marker",
                "args": {
                    "marker_type": request.marker_type,
                    "cue_id": request.cue_id,
                    "action_id": request.action_id,
                }
            }),
            "marker",
        )?;
    }
    Ok(format!("MARKER_ACK:{}", request.marker_type))
}

#[tauri::command]
pub fn recorder_get_status(
    shared: SharedHandle<'_>,
    engine: EngineHandle<'_>,
    app: AppHandle,
) -> Result<RecorderStatus, String> {
    let shared_guard = lock(&shared)?;
    let mut engine_guard = lock_engine(&engine)?;
    if ensure_spawned(&mut engine_guard, &app) {
        if let Ok(telemetry) =
            engine_ok(host_of(&mut engine_guard), json!({"op": "status"}), "status")
        {
            return Ok(merged_status(&shared_guard, &telemetry));
        }
    }
    Ok(status_of(&*shared_guard))
}

#[tauri::command]
pub fn recorder_get_capabilities(
    engine: EngineHandle<'_>,
    app: AppHandle,
) -> Result<NativeCapabilities, String> {
    let mut engine_guard = lock_engine(&engine)?;
    if ensure_spawned(&mut engine_guard, &app) {
        return probe_native_capabilities(host_of(&mut engine_guard));
    }
    Ok(NativeCapabilities {
        wgc_available: false,   // no sidecar → no desktop capture path
        nvenc_available: false, // true only after a real NVENC probe
        wasapi_available: false, // P1 locked false per Principle F
        disk_free_gb: 0.0,
        output_writable: false,
    })
}
