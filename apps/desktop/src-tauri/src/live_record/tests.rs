//! P0 gate tests — LIVE_RECORD_P0_ARCHITECTURE_FROZEN
//!
//! Rust-side counterpart of `frontend/app/src/features/live-record/__tests__/p0Contracts.test.ts`.
//! These exercise the same core paths the Tauri commands delegate to.

use super::commands::*;
use super::state::*;
use super::ALLOWED_RECORDER_COMMANDS;
use super::{
    MarkerRequest, MuteRequest, RecorderPrepareRequest, RecorderProfile,
    RecorderStartRequest,
};

fn prepare_request(plan_hash: &str) -> RecorderPrepareRequest {
    RecorderPrepareRequest {
        execution_plan_id: "plan-001".into(),
        execution_plan_hash: plan_hash.into(),
        episode_id: "ep-001".into(),
        output_dir: "D:/recordings".into(),
        profile: RecorderProfile::default(), // quality-first V2 defaults
    }
}

// ─── State machine transition table ──────────────────────────────────────────

#[test]
fn idle_to_recording_is_rejected() {
    assert!(!can_transition(LiveRecordState::Idle, LiveRecordState::Recording));
    assert!(assert_transition(LiveRecordState::Idle, LiveRecordState::Recording)
        .unwrap_err()
        .starts_with("LIVE_RECORD_STATE_TRANSITION_REJECTED"));
}

#[test]
fn recording_must_finalize_before_completing() {
    assert!(can_transition(
        LiveRecordState::Recording,
        LiveRecordState::Finalizing
    ));
    assert!(!can_transition(
        LiveRecordState::Recording,
        LiveRecordState::Completed
    ));
    assert!(!can_transition(
        LiveRecordState::Recording,
        LiveRecordState::Idle
    ));
}

#[test]
fn completed_returns_to_idle() {
    assert!(can_transition(
        LiveRecordState::Completed,
        LiveRecordState::Idle
    ));
}

#[test]
fn every_state_has_a_transitions_entry() {
    for state in LiveRecordState::ALL {
        let found = LIVE_RECORD_TRANSITIONS
            .iter()
            .filter(|(from, _)| *from == state)
            .count();
        assert_eq!(found, 1, "{:?} must appear exactly once", state);
    }
    assert_eq!(LIVE_RECORD_TRANSITIONS.len(), LiveRecordState::ALL.len());
}

#[test]
fn blocked_recovers_through_preparing() {
    assert!(can_transition(
        LiveRecordState::Blocked,
        LiveRecordState::Preparing
    ));
    assert!(!can_transition(
        LiveRecordState::Blocked,
        LiveRecordState::Recording
    ));
}

// ─── Command allowlist ───────────────────────────────────────────────────────

#[test]
fn allowed_commands_mirror_ts_contract() {
    // RecorderCommand union (+ capability/source probes) in contracts/ipc.ts (V2)
    assert_eq!(
        ALLOWED_RECORDER_COMMANDS,
        &[
            "recorder_prepare",
            "recorder_start",
            "recorder_pause",
            "recorder_resume",
            "recorder_stop",
            "recorder_get_status",
            "recorder_create_marker",
            "recorder_mute",
            "recorder_recover",
            "recorder_get_capabilities",
            "recorder_get_sources",
        ]
    );
}

// ─── Prepare validation (fail-closed) ────────────────────────────────────────

#[test]
fn prepare_rejects_non_sha256_hash() {
    let mut shared = RecorderSharedState::default();
    assert!(prepare_core(&mut shared, &prepare_request("abc")).is_err());
    assert!(prepare_core(&mut shared, &prepare_request(&"g".repeat(64))).is_err());

    // Valid hash but wrong length is still rejected.
    assert!(prepare_core(&mut shared, &prepare_request("a".repeat(63).as_str())).is_err());
    // Nothing mutated on rejection.
    assert_eq!(shared.state, LiveRecordState::Idle);
}

#[test]
fn sidecar_prepare_args_forward_v2_profile_verbatim() {
    // V2: the profile mirrors EngineProfile field-for-field and reaches the
    // sidecar unmodified — the engine validator is the single source of truth.
    let req = prepare_request(&"a".repeat(64));
    let args = sidecar_prepare_args(&req).unwrap();
    assert_eq!(args["op"], "prepare");
    assert_eq!(args["args"]["execution_plan_id"], "plan-001");
    let profile = &args["args"]["profile"];
    assert_eq!(profile["capture_source"]["kind"], "DISPLAY");
    assert_eq!(profile["video"]["encoder"], "NVENC");
    assert_eq!(profile["video"]["rate_control"], "CQP");
    assert_eq!(profile["video"]["fps"], 60);
    assert_eq!(profile["audio"]["sample_rate"], 48000);
    assert_eq!(profile["audio"]["microphone"]["enabled"], true);
    assert_eq!(profile["container"]["format"], "MKV");
    assert_eq!(profile["container"]["segment_minutes"], 5);
}

#[test]
fn mute_requires_an_active_take() {
    let shared = RecorderSharedState::default();
    let req = MuteRequest { mic_muted: true, system_muted: false };
    assert!(mute_core(&shared, &req)
        .unwrap_err()
        .starts_with("RECORDER_MUTE_REJECTED"));
}

#[test]
fn recover_is_rejected_during_an_active_take() {
    let mut shared = RecorderSharedState::default();
    // IDLE → allowed by the gate (the engine still fails closed without files).
    assert!(recover_gate(&shared).is_ok());

    shared.state = LiveRecordState::Recording;
    assert!(recover_gate(&shared)
        .unwrap_err()
        .starts_with("RECORDER_RECOVER_REJECTED"));

    shared.state = LiveRecordState::Paused;
    assert!(recover_gate(&shared).is_err());

    shared.state = LiveRecordState::Finalizing;
    assert!(recover_gate(&shared).is_err());
}

#[test]
fn prepare_lands_blocked_with_native_blockers() {
    // P0 capabilities are all false → fail closed into BLOCKED.
    let mut shared = RecorderSharedState::default();
    let result = prepare_core(&mut shared, &prepare_request(&"a".repeat(64))).unwrap();
    assert_eq!(result, "PREPARED:plan-001");
    assert_eq!(shared.state, LiveRecordState::Blocked);
    assert_eq!(shared.blockers, vec!["WGC_UNAVAILABLE", "NVENC_UNAVAILABLE"]);
    assert_eq!(shared.execution_plan_id.as_deref(), Some("plan-001"));
}

#[test]
fn prepare_from_completed_is_rejected() {
    let mut shared = RecorderSharedState::default();
    shared.state = LiveRecordState::Completed;
    assert!(prepare_core(&mut shared, &prepare_request(&"a".repeat(64))).is_err());
}

// ─── Start / pause / resume / stop lifecycle ─────────────────────────────────

#[test]
fn start_fails_closed_while_blocked() {
    let mut shared = RecorderSharedState::default();
    prepare_core(&mut shared, &prepare_request(&"a".repeat(64))).unwrap();
    assert_eq!(shared.state, LiveRecordState::Blocked);

    let req = RecorderStartRequest {
        execution_plan_id: "plan-001".into(),
        take_id: None,
    };
    let err = start_core(&mut shared, &req).unwrap_err();
    assert!(err.starts_with("RECORDER_NOT_READY"), "{err}");
    assert_eq!(shared.state, LiveRecordState::Blocked);
}

#[test]
fn start_rejects_plan_mismatch() {
    let mut shared = RecorderSharedState::default();
    shared.state = LiveRecordState::Ready;
    shared.execution_plan_id = Some("plan-001".into());
    let req = RecorderStartRequest {
        execution_plan_id: "plan-999".into(),
        take_id: None,
    };
    assert_eq!(
        start_core(&mut shared, &req).unwrap_err(),
        "RECORDER_PLAN_MISMATCH: execution_plan_id does not match prepared plan"
    );
}

#[test]
fn recording_lifecycle_pause_resume_stop() {
    let mut shared = RecorderSharedState::default();
    shared.state = LiveRecordState::Ready;
    shared.execution_plan_id = Some("plan-001".into());

    let take_id = start_core(
        &mut shared,
        &RecorderStartRequest {
            execution_plan_id: "plan-001".into(),
            take_id: Some("take_0001".into()),
        },
    )
    .unwrap();
    assert_eq!(take_id, "take_0001");
    assert_eq!(shared.state, LiveRecordState::Recording);

    pause_core(&mut shared).unwrap();
    assert_eq!(shared.state, LiveRecordState::Paused);

    resume_core(&mut shared).unwrap();
    assert_eq!(shared.state, LiveRecordState::Recording);

    stop_core(&mut shared).unwrap();
    assert_eq!(shared.state, LiveRecordState::Completed);
}

#[test]
fn stop_without_recording_is_rejected() {
    let mut shared = RecorderSharedState::default();
    let err = stop_core(&mut shared).unwrap_err();
    assert!(err.starts_with("RECORDER_NOT_RECORDING"), "{err}");
}

// ─── Markers ─────────────────────────────────────────────────────────────────

#[test]
fn markers_require_recording_or_paused() {
    let mut shared = RecorderSharedState::default();
    let marker = MarkerRequest {
        marker_type: "TAKE_START".into(),
        cue_id: None,
        action_id: None,
    };
    assert!(create_marker_core(&shared, &marker)
        .unwrap_err()
        .starts_with("RECORDER_MARKER_REJECTED"));

    shared.state = LiveRecordState::Recording;
    assert_eq!(
        create_marker_core(&shared, &marker).unwrap(),
        "MARKER_ACK:TAKE_START"
    );

    shared.state = LiveRecordState::Paused;
    assert!(create_marker_core(&shared, &marker).is_ok());
}

#[test]
fn markers_require_type() {
    let mut shared = RecorderSharedState::default();
    shared.state = LiveRecordState::Recording;
    let marker = MarkerRequest {
        marker_type: String::new(),
        cue_id: None,
        action_id: None,
    };
    assert!(create_marker_core(&shared, &marker).is_err());
}

// ─── Status projection ───────────────────────────────────────────────────────

#[test]
fn status_reports_real_state_and_blockers() {
    let mut shared = RecorderSharedState::default();
    let status = status_of(&shared);
    assert_eq!(status.state.as_str(), "IDLE");
    assert!(status.blockers.is_none());

    prepare_core(&mut shared, &prepare_request(&"a".repeat(64))).unwrap();
    let status = status_of(&shared);
    assert_eq!(status.state.as_str(), "BLOCKED");
    assert_eq!(
        status.blockers,
        Some(vec![
            "WGC_UNAVAILABLE".to_string(),
            "NVENC_UNAVAILABLE".to_string()
        ])
    );
}

// ─── Supervision guards (engine respawn / mid-take death) ────────────────────

#[test]
fn respawn_only_from_take_free_states() {
    use LiveRecordState as S;
    // Take-free states: a fresh sidecar is legitimate.
    for free in [S::Idle, S::Blocked, S::Completed, S::Failed] {
        assert!(respawn_allowed(free), "{} must allow respawn", free.as_str());
    }
    // Everything else may carry a live take: respawning would silently swap
    // the data plane out from under the session.
    for live in [
        S::Preparing,
        S::Preflight,
        S::Ready,
        S::Recording,
        S::Paused,
        S::DirectorDegraded,
        S::Recovering,
        S::Finalizing,
    ] {
        assert!(!respawn_allowed(live), "{} must not respawn", live.as_str());
    }
}

#[test]
fn dead_engine_error_names_the_session_state() {
    let msg = dead_engine_mid_take(LiveRecordState::Recording);
    assert!(msg.starts_with("ENGINE_DEAD_MID_TAKE"), "{msg}");
    assert!(msg.contains("RECORDING"), "{msg}");
}
