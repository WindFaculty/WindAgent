//! Live Record session state machine — Phase 0 Frozen
//! Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN
//!
//! Exact Rust mirror of the frozen transition table in
//! `frontend/app/src/features/live-record/domain/stateMachine.ts`.
//! This is a contract mirror, not a reimplementation: any change requires
//! editing both sides plus a version bump on the gate doc.

use serde::{Deserialize, Serialize};

/// Session states — mirrors `LiveRecordSessionStatus` in `domain/types.ts`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum LiveRecordState {
    #[default]
    Idle,
    Preparing,
    Preflight,
    Ready,
    Recording,
    Paused,
    DirectorDegraded,
    Recovering,
    Finalizing,
    Completed,
    Failed,
    Blocked,
}

impl LiveRecordState {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Idle => "IDLE",
            Self::Preparing => "PREPARING",
            Self::Preflight => "PREFLIGHT",
            Self::Ready => "READY",
            Self::Recording => "RECORDING",
            Self::Paused => "PAUSED",
            Self::DirectorDegraded => "DIRECTOR_DEGRADED",
            Self::Recovering => "RECOVERING",
            Self::Finalizing => "FINALIZING",
            Self::Completed => "COMPLETED",
            Self::Failed => "FAILED",
            Self::Blocked => "BLOCKED",
        }
    }

    /// Every state must appear exactly once in [`LIVE_RECORD_TRANSITIONS`].
    pub const ALL: [Self; 12] = [
        Self::Idle,
        Self::Preparing,
        Self::Preflight,
        Self::Ready,
        Self::Recording,
        Self::Paused,
        Self::DirectorDegraded,
        Self::Recovering,
        Self::Finalizing,
        Self::Completed,
        Self::Failed,
        Self::Blocked,
    ];
}

/// Allowed transitions — deterministic. No wildcard jumps.
/// Mirrors `LIVE_RECORD_TRANSITIONS` in `domain/stateMachine.ts` line-for-line.
pub const LIVE_RECORD_TRANSITIONS: &[(LiveRecordState, &[LiveRecordState])] = &[
    (LiveRecordState::Idle, &[LiveRecordState::Preparing]),
    (
        LiveRecordState::Preparing,
        &[
            LiveRecordState::Preflight,
            LiveRecordState::Failed,
            LiveRecordState::Blocked,
        ],
    ),
    (
        LiveRecordState::Preflight,
        &[
            LiveRecordState::Ready,
            LiveRecordState::Blocked,
            LiveRecordState::Failed,
        ],
    ),
    (
        LiveRecordState::Ready,
        &[
            LiveRecordState::Recording,
            LiveRecordState::Blocked,
            LiveRecordState::Failed,
        ],
    ),
    (
        LiveRecordState::Recording,
        &[
            LiveRecordState::Paused,
            LiveRecordState::DirectorDegraded,
            LiveRecordState::Recovering,
            LiveRecordState::Finalizing,
            LiveRecordState::Failed,
        ],
    ),
    (
        LiveRecordState::Paused,
        &[
            LiveRecordState::Recording,
            LiveRecordState::Finalizing,
            LiveRecordState::Failed,
        ],
    ),
    (
        LiveRecordState::DirectorDegraded,
        &[
            LiveRecordState::Recovering,
            LiveRecordState::Paused,
            LiveRecordState::Finalizing,
            LiveRecordState::Failed,
        ],
    ),
    (
        LiveRecordState::Recovering,
        &[
            LiveRecordState::Recording,
            LiveRecordState::DirectorDegraded,
            LiveRecordState::Paused,
            LiveRecordState::Failed,
        ],
    ),
    (
        LiveRecordState::Finalizing,
        &[
            LiveRecordState::Completed,
            LiveRecordState::Failed,
        ],
    ),
    (LiveRecordState::Completed, &[LiveRecordState::Idle]),
    (
        LiveRecordState::Failed,
        &[LiveRecordState::Idle, LiveRecordState::Preparing],
    ),
    (
        LiveRecordState::Blocked,
        &[LiveRecordState::Preparing, LiveRecordState::Idle],
    ),
];

pub fn allowed_transitions(from: LiveRecordState) -> &'static [LiveRecordState] {
    LIVE_RECORD_TRANSITIONS
        .iter()
        .find(|(state, _)| *state == from)
        .map(|(_, next)| *next)
        .unwrap_or(&[])
}

pub fn can_transition(from: LiveRecordState, to: LiveRecordState) -> bool {
    allowed_transitions(from).contains(&to)
}

pub fn assert_transition(from: LiveRecordState, to: LiveRecordState) -> Result<(), String> {
    if can_transition(from, to) {
        Ok(())
    } else {
        Err(format!(
            "LIVE_RECORD_STATE_TRANSITION_REJECTED: {} -> {} not allowed",
            from.as_str(),
            to.as_str()
        ))
    }
}

/// Shared recorder control-plane state, managed by Tauri and guarded by a
/// `std::sync::Mutex`. P0 holds no real telemetry — capture/encoding lands in
/// Phase 8-9 inside the native engine, never here (Principle D).
#[derive(Debug, Default)]
pub struct RecorderSharedState {
    pub state: LiveRecordState,
    pub execution_plan_id: Option<String>,
    pub execution_plan_hash: Option<String>,
    pub take_id: Option<String>,
    /// Preflight blocker codes (`PreflightBlockerCode` in domain/stateMachine.ts).
    pub blockers: Vec<String>,
}
