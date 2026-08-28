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
    CaptureSources, MarkerRequest, MonitorSource, MuteRequest, NativeCapabilities, RecoverRequest,
    RecorderPrepareRequest, RecorderStartRequest, RecorderStatus,
};

// ─── Core logic (pure over shared state — unit-testable) ─────────────────────

fn is_sha256_hex(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit())
}

/// Validate a prepare payload without touching state — shared by both paths.
///
/// V2: profile semantics (NVENC-only, CQP, MKV segmentation, multi-track
/// audio) are validated fail-closed by the engine sidecar's own validator —
/// the control plane only guards identity fields and never re-interprets
/// encoder settings (Principle D).
pub(crate) fn validate_prepare_request(
    request: &RecorderPrepareRequest,
) -> Result<(), String> {
    if request.execution_plan_id.is_empty() || request.episode_id.is_empty() {
        return Err("RECORDER_PREPARE_REJECTED: missing execution_plan_id/episode_id".into());
    }
    if !is_sha256_hex(&request.execution_plan_hash) {
        return Err("RECORDER_PREPARE_REJECTED: plan_hash must be sha256 hex".into());
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

/// V2 (§11): mute toggles reach the recorder itself — they require an active
/// take (RECORDING/PAUSED); muting meters only is forbidden.
pub(crate) fn mute_core(
    shared: &RecorderSharedState,
    _request: &MuteRequest,
) -> Result<(), String> {
    if !matches!(
        shared.state,
        LiveRecordState::Recording | LiveRecordState::Paused
    ) {
        return Err(format!(
            "RECORDER_MUTE_REJECTED: mute requires RECORDING/PAUSED, current {}",
            shared.state.as_str()
        ));
    }
    Ok(())
}

/// V2 (§15): crash recovery scans a take directory and rebuilds its manifest.
/// It must never run while a take is live — the engine would be rewriting the
/// very segments recovery wants to validate.
pub(crate) fn recover_gate(shared: &RecorderSharedState) -> Result<(), String> {
    if matches!(
        shared.state,
        LiveRecordState::Recording | LiveRecordState::Paused | LiveRecordState::Finalizing
    ) {
        return Err(format!(
            "RECORDER_RECOVER_REJECTED: cannot recover during an active take ({})",
            shared.state.as_str()
        ));
    }
    Ok(())
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
        capture_fps: 0.0,
        encode_fps: 0.0,
        av_sync_error_ms: None,
        mic_drift_ppm: None,
        system_drift_ppm: None,
        resource_stage: "normal".into(),
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

/// Session states in which spawning (or respawning) an engine is legitimate —
/// no take can be live in them. Mid-take a dead sidecar is a crash to surface,
/// never to paper over with a fresh Idle process that knows nothing about the
/// prepared plan or the running take.
pub(crate) fn respawn_allowed(state: LiveRecordState) -> bool {
    matches!(
        state,
        LiveRecordState::Idle
            | LiveRecordState::Blocked
            | LiveRecordState::Completed
            | LiveRecordState::Failed
    )
}

/// Error for "engine gone while a take is live" — the session must land in
/// FAILED instead of continuing against a data plane that no longer exists.
pub(crate) fn dead_engine_mid_take(state: LiveRecordState) -> String {
    format!(
        "ENGINE_DEAD_MID_TAKE: recording engine is not running and must not respawn from {} \
         (recover the take on next launch, then re-prepare)",
        state.as_str()
    )
}

/// Make sure a live host exists (spawning it on first use); the caller then
/// borrows it with `host_of`. Split in two so no borrow is held across the
/// spawn. `allow_respawn=false` turns silent replacement off — callers in a
/// take-live context check [`respawn_allowed`] themselves and surface
/// [`dead_engine_mid_take`] instead.
fn ensure_spawned(engine: &mut EngineGuard<'_>, app: &AppHandle, allow_respawn: bool) -> bool {
    let alive = matches!(engine.as_ref(), Some(host) if host.is_alive());
    if alive {
        return true;
    }
    if !allow_respawn {
        return false;
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

/// Build the sidecar's `prepare` args. The V2 profile mirrors the engine's
/// `EngineProfile` field-for-field, so it is serialized verbatim — the sidecar
/// validator stays the single source of truth for every encoder setting.
pub(crate) fn sidecar_prepare_args(request: &RecorderPrepareRequest) -> Result<Value, String> {
    let profile = serde_json::to_value(&request.profile)
        .map_err(|e| format!("RECORDER_PREPARE_REJECTED: profile serialize failed: {e}"))?;
    Ok(json!({
        "op": "prepare",
        "args": {
            "execution_plan_id": request.execution_plan_id,
            "execution_plan_hash": request.execution_plan_hash,
            "episode_id": request.episode_id,
            "output_dir": request.output_dir,
            "profile": profile,
        }
    }))
}

/// The V2 `EngineCapabilities` shape is mirrored 1:1 by [`NativeCapabilities`],
/// so a real probe round-trips through serde without any remapping. Missing
/// fields deserialize to defaults (false/0/empty) which fail closed in the
/// preflight gate below.
fn sidecar_capabilities_to_native(payload: &Value) -> Result<NativeCapabilities, String> {
    serde_json::from_value(payload.clone())
        .map_err(|e| format!("ENGINE_MALFORMED_RESPONSE: capabilities decode failed: {e}"))
}

fn probe_native_capabilities(host: &mut EngineHost) -> Result<NativeCapabilities, String> {
    let payload = engine_ok(host, json!({"op": "capabilities"}), "capabilities")?;
    // A simulation sidecar is never usable from the production control plane —
    // refuse it here so prepare/start/capabilities all fail closed on `mock`.
    if payload.get("backend").and_then(Value::as_str) == Some("mock") {
        return Err(
            "ENGINE_MOCK_BACKEND_REFUSED: simulation backend is not allowed in production"
                .into(),
        );
    }
    sidecar_capabilities_to_native(&payload)
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
    // §17 real telemetry — measured values only; absent probes stay None/zero.
    status.capture_fps =
        telemetry.get("capture_fps").and_then(Value::as_f64).unwrap_or(0.0) as f32;
    status.encode_fps =
        telemetry.get("encode_fps").and_then(Value::as_f64).unwrap_or(0.0) as f32;
    status.av_sync_error_ms = telemetry.get("av_sync_error_ms").and_then(Value::as_f64);
    status.mic_drift_ppm = telemetry.get("mic_drift_ppm").and_then(Value::as_f64);
    status.system_drift_ppm = telemetry.get("system_drift_ppm").and_then(Value::as_f64);
    if let Some(stage) = telemetry.get("resource_stage").and_then(Value::as_str) {
        status.resource_stage = stage.to_string();
    }
    status.current_segment_index =
        telemetry.get("current_segment_index").and_then(Value::as_u64).map(|i| i as u32);
    status.disk_write_mbps =
        Some(telemetry.get("disk_write_mbps").and_then(Value::as_f64).unwrap_or(0.0) as f32);
    status.bitrate_mbps =
        telemetry.get("bitrate_mbps").and_then(Value::as_f64).unwrap_or(0.0) as f32;
    if let Some(nvenc) = telemetry.get("nvenc_status").and_then(Value::as_str) {
        status.nvenc_status = nvenc.to_string();
    }
    if let Some(state) = telemetry.get("state").and_then(Value::as_str) {
        // Engine states arrive lowercase (ServiceState::as_str). Transient
        // ones (`probing`/`preparing`/`recovering`) and failures stay with
        // the session machine's own view — it owns those phase transitions.
        status.state = match state {
            "recording" => LiveRecordState::Recording,
            "paused" => LiveRecordState::Paused,
            "completed" | "finalizing" => LiveRecordState::Completed,
            "ready" if shared.state == LiveRecordState::Ready => LiveRecordState::Ready,
            "idle" if shared.state == LiveRecordState::Idle => LiveRecordState::Idle,
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

    // Prepare only ever runs from quiescent states (the transition gate below
    // enforces it), so a fresh spawn is always legitimate here.
    if ensure_spawned(&mut engine_guard, &app, true) {
        let capabilities = probe_native_capabilities(host_of(&mut engine_guard))?;

        assert_transition(shared_guard.state, LiveRecordState::Preparing)?;
        shared_guard.blockers.clear();
        shared_guard.state = LiveRecordState::Preparing;

        assert_transition(shared_guard.state, LiveRecordState::Preflight)?;
        shared_guard.state = LiveRecordState::Preflight;

        // V2 gate: the engine itself decides availability from the full native
        // stack (D3D11 + WGC + NVENC + audio paths); no per-field re-check here.
        if capabilities.engine_available {
            let args = sidecar_prepare_args(&request)?;
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
        shared_guard.blockers = capabilities.blockers.clone();
        if shared_guard.blockers.is_empty() {
            shared_guard.blockers = vec!["ENGINE_UNAVAILABLE".into()];
        }
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
    // Starting must talk to the engine that was prepared — never spawn a fresh
    // one behind the session's back. A dead host in READY is a failed prepare
    // continuation: fail closed instead of recording into nothing.
    let spawned = ensure_spawned(&mut engine_guard, &app, false);
    if !spawned && !respawn_allowed(shared_guard.state) {
        return Err(dead_engine_mid_take(shared_guard.state));
    }
    if spawned {
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
    let spawned = ensure_spawned(&mut engine_guard, &app, false);
    if !spawned && !respawn_allowed(shared_guard.state) {
        return Err(dead_engine_mid_take(shared_guard.state));
    }
    if spawned {
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
    let spawned = ensure_spawned(&mut engine_guard, &app, false);
    if !spawned && !respawn_allowed(shared_guard.state) {
        return Err(dead_engine_mid_take(shared_guard.state));
    }
    if spawned {
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
    let spawned = ensure_spawned(&mut engine_guard, &app, false);
    if spawned {
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
    if !respawn_allowed(shared_guard.state) {
        // Mid-take with a dead engine: the tail segment was never committed and
        // no finalize can happen. Land FAILED honestly — the crash-safe prefix
        // plus recovery rebuild salvage what was flushed.
        shared_guard.blockers.push("ENGINE_DEAD_MID_TAKE".into());
        assert_transition(shared_guard.state, LiveRecordState::Finalizing)?;
        shared_guard.state = LiveRecordState::Finalizing;
        assert_transition(shared_guard.state, LiveRecordState::Failed)?;
        shared_guard.state = LiveRecordState::Failed;
        return Err(dead_engine_mid_take(shared_guard.state));
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
    let shared_guard = lock(&shared)?;
    create_marker_core(&shared_guard, &request)?; // same gating either way

    let mut engine_guard = lock_engine(&engine)?;
    // Markers are mid-take by definition (core gate enforces RECORDING/PAUSED)
    // — a dead engine must surface, not respawn.
    if !ensure_spawned(&mut engine_guard, &app, false) {
        return Err(dead_engine_mid_take(shared_guard.state));
    }
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
    Ok(format!("MARKER_ACK:{}", request.marker_type))
}

/// V2 (§11): recorder-level mute — the toggle reaches the data plane so the
/// MKV tracks genuinely fall silent; UI meters reflect the same state.
#[tauri::command]
pub fn recorder_mute(
    request: MuteRequest,
    shared: SharedHandle<'_>,
    engine: EngineHandle<'_>,
    app: AppHandle,
) -> Result<(), String> {
    let shared_guard = lock(&shared)?;
    mute_core(&shared_guard, &request)?;

    let mut engine_guard = lock_engine(&engine)?;
    // Mute is a data-plane toggle mid-take — no silent respawn either.
    if !ensure_spawned(&mut engine_guard, &app, false) {
        return Err(dead_engine_mid_take(shared_guard.state));
    }
    engine_ok(
        host_of(&mut engine_guard),
        json!({
            "op": "mute",
            "args": {
                "mic_muted": request.mic_muted,
                "system_muted": request.system_muted,
            }
        }),
        "mute",
    )?;
    Ok(())
}

/// V2 (§15): scan a take directory for an interrupted recording, validate
/// completed segments, rebuild the manifest, drop only the unfinished tail.
#[tauri::command]
pub fn recorder_recover(
    request: RecoverRequest,
    shared: SharedHandle<'_>,
    engine: EngineHandle<'_>,
    app: AppHandle,
) -> Result<Value, String> {
    let shared_guard = lock(&shared)?;
    recover_gate(&shared_guard)?;

    let mut engine_guard = lock_engine(&engine)?;
    if ensure_spawned(&mut engine_guard, &app, respawn_allowed(shared_guard.state)) {
        return engine_ok(
            host_of(&mut engine_guard),
            json!({
                "op": "recover",
                "args": { "output_dir": request.output_dir }
            }),
            "recover",
        );
    }
    // No sidecar: nothing to recover from — fail closed with an explicit code
    // rather than pretending success.
    Err("ENGINE_UNAVAILABLE: no recording engine sidecar to recover with".into())
}

#[tauri::command]
pub fn recorder_get_status(
    shared: SharedHandle<'_>,
    engine: EngineHandle<'_>,
    app: AppHandle,
) -> Result<RecorderStatus, String> {
    let shared_guard = lock(&shared)?;
    let mut engine_guard = lock_engine(&engine)?;
    let spawned = ensure_spawned(&mut engine_guard, &app, respawn_allowed(shared_guard.state));
    if spawned {
        // Never swallow an engine failure into a healthy-looking status: the
        // session view stays authoritative and the fault lands as a blocker.
        match engine_ok(host_of(&mut engine_guard), json!({"op": "status"}), "status") {
            Ok(telemetry) => return Ok(merged_status(&shared_guard, &telemetry)),
            Err(e) => {
                let mut status = status_of(&*shared_guard);
                status
                    .blockers
                    .get_or_insert_with(Vec::new)
                    .push(format!("ENGINE_STATUS_FAILED:{e}"));
                return Ok(status);
            }
        }
    }
    let mut status = status_of(&*shared_guard);
    if !respawn_allowed(shared_guard.state) {
        // Engine dead mid-take — say so instead of a silent all-zero status.
        status
            .blockers
            .get_or_insert_with(Vec::new)
            .push("ENGINE_DEAD_MID_TAKE".into());
    }
    Ok(status)
}

#[tauri::command]
pub fn recorder_get_capabilities(
    engine: EngineHandle<'_>,
    app: AppHandle,
) -> Result<NativeCapabilities, String> {
    let mut engine_guard = lock_engine(&engine)?;
    // Probe-only command — never carries take state, so respawning is safe.
    if ensure_spawned(&mut engine_guard, &app, true) {
        return probe_native_capabilities(host_of(&mut engine_guard));
    }
    // No sidecar: everything unavailable — the all-defaults probe fails closed.
    Ok(NativeCapabilities {
        blockers: vec!["ENGINE_UNAVAILABLE".into()],
        ..Default::default()
    })
}

/// §17 source picker data — real monitor/window enumeration from the engine.
/// Read-only like the capability probe, so respawning is always legitimate.
#[tauri::command]
pub fn recorder_get_sources(
    engine: EngineHandle<'_>,
    app: AppHandle,
) -> Result<CaptureSources, String> {
    let mut engine_guard = lock_engine(&engine)?;
    if ensure_spawned(&mut engine_guard, &app, true) {
        let payload = engine_ok(host_of(&mut engine_guard), json!({"op": "sources"}), "sources")?;
        return serde_json::from_value(payload)
            .map_err(|e| format!("ENGINE_MALFORMED_RESPONSE: sources decode failed: {e}"));
    }
    // No sidecar (web dev / CI): the primary display stays the honest default
    // target and no windows are claimed.
    Ok(CaptureSources {
        monitors: vec![MonitorSource {
            kind: "DISPLAY".into(),
            id: String::new(),
            label: "Primary display".into(),
            width: 0,
            height: 0,
            is_primary: true,
        }],
        windows: Vec::new(),
    })
}
