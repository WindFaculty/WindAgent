//! Recorder control-plane commands — Phase 0 stubs.
//! Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN
//!
//! P0 commands validate payload shape and drive the frozen state machine only.
//! Real capture/encode/mux work lives in the native engine sidecar (Phase 8-9)
//! and is never inlined here. Fail-closed: with WGC/NVENC probes still absent,
//! prepare always lands in BLOCKED, so start can never succeed.
//!
//! Each command delegates to a plain `*_core` function over
//! `&mut RecorderSharedState` so gate tests in `tests.rs` exercise the exact
//! same code paths without a Tauri runtime.

use std::sync::Mutex;

use tauri::State;

use super::state::{assert_transition, can_transition, LiveRecordState, RecorderSharedState};
use super::types::{
    MarkerRequest, NativeCapabilities, RecorderPrepareRequest, RecorderStartRequest,
    RecorderStatus,
};

// ─── Core logic (pure over shared state — unit-testable) ─────────────────────

fn is_sha256_hex(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit())
}

/// IDLE/BLOCKED/FAILED → PREPARING → PREFLIGHT → BLOCKED (P0 capabilities are all false).
pub(crate) fn prepare_core(
    shared: &mut RecorderSharedState,
    request: &RecorderPrepareRequest,
) -> Result<String, String> {
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

    assert_transition(shared.state, LiveRecordState::Preparing)?;
    shared.execution_plan_id = Some(request.execution_plan_id.clone());
    shared.execution_plan_hash = Some(request.execution_plan_hash.clone());
    shared.blockers.clear();
    shared.state = LiveRecordState::Preparing;

    assert_transition(shared.state, LiveRecordState::Preflight)?;
    shared.state = LiveRecordState::Preflight;

    // P0 preflight: WGC/NVENC probes land with the native engine (Phase 8),
    // so native capabilities report unavailable → fail closed into BLOCKED.
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

/// RECORDING|PAUSED → FINALIZING → COMPLETED (instant stub; real finalize is Phase 9).
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

/// Markers are only meaningful while recording or paused; timeline writes land
/// with the engine (Phase 8+), so P0 just acknowledges.
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

// ─── Tauri commands ──────────────────────────────────────────────────────────

type SharedHandle<'a> = State<'a, Mutex<RecorderSharedState>>;

fn lock<'a>(shared: &'a SharedHandle<'_>) -> Result<std::sync::MutexGuard<'a, RecorderSharedState>, String> {
    shared.lock().map_err(|_| "RECORDER_STATE_POISONED".to_string())
}

#[tauri::command]
pub fn recorder_prepare(
    request: RecorderPrepareRequest,
    shared: SharedHandle<'_>,
) -> Result<String, String> {
    prepare_core(&mut *lock(&shared)?, &request)
}

#[tauri::command]
pub fn recorder_start(
    request: RecorderStartRequest,
    shared: SharedHandle<'_>,
) -> Result<String, String> {
    start_core(&mut *lock(&shared)?, &request)
}

#[tauri::command]
pub fn recorder_pause(shared: SharedHandle<'_>) -> Result<(), String> {
    pause_core(&mut *lock(&shared)?)
}

#[tauri::command]
pub fn recorder_resume(shared: SharedHandle<'_>) -> Result<(), String> {
    resume_core(&mut *lock(&shared)?)
}

#[tauri::command]
pub fn recorder_stop(shared: SharedHandle<'_>) -> Result<String, String> {
    stop_core(&mut *lock(&shared)?)
}

#[tauri::command]
pub fn recorder_create_marker(
    request: MarkerRequest,
    shared: SharedHandle<'_>,
) -> Result<String, String> {
    create_marker_core(&*lock(&shared)?, &request)
}

#[tauri::command]
pub fn recorder_get_status(shared: SharedHandle<'_>) -> Result<RecorderStatus, String> {
    Ok(status_of(&*lock(&shared)?))
}

#[tauri::command]
pub fn recorder_get_capabilities() -> NativeCapabilities {
    NativeCapabilities {
        wgc_available: false,   // true only after WGC probe in Phase 8
        nvenc_available: false, // true only after NVENC probe in Phase 9
        wasapi_available: false, // P0 locked false per Principle F
        disk_free_gb: 0.0,
        output_writable: false,
    }
}
