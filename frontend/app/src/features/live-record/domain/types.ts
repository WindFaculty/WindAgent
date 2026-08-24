/**
 * Live Record Domain Contracts — Phase 0 Frozen
 * Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN
 *
 * Defines the immutable Episode -> LiveExecutionPlan -> RecordingTake lineage.
 * All Gemini actions must reference PreparedAction via action_id only — no
 * arbitrary code/command payloads in tool calls (Principle C).
 */

// ─── Plan lifecycle ──────────────────────────────────────────────────────────

export type LiveExecutionPlanStatus =
  | 'DRAFT'
  | 'PREPARED'
  | 'VALIDATED'
  | 'FROZEN'
  | 'STALE'
  | 'INVALID';

export type PreparedActionType =
  | 'CODE_PLAYBACK'
  | 'BROWSER_NAVIGATION'
  | 'BROWSER_ACTION'
  | 'RUN_COMMAND'
  | 'TOOL_RUN'
  | 'OPEN_FILE'
  | 'VISUAL_VERIFY'
  | 'SCENE_CONTROL'
  | 'MARKER';

export type TypingMode = 'TYPE' | 'PASTE';

export interface ExpectedVisualState {
  readonly state_id: string;
  readonly description: string;
  readonly url_contains?: string;
  readonly file_should_contain_hash?: string;
  readonly test_should_pass?: boolean;
  readonly screenshot_ref?: string;
}

export interface PreparedAction {
  readonly action_id: string;
  readonly type: PreparedActionType;
  readonly scene_id: string;
  readonly cue_id?: string;
  /** Immutable payload reference — content lives in artifact store, not in tool args */
  readonly payload_ref: string; // artifact://...
  readonly target_file?: string;
  readonly before_hash?: string;
  readonly after_hash?: string;
  readonly typing_mode?: TypingMode;
  readonly chars_per_second?: number;
  readonly browser_semantic_target?: string;
  readonly command_ref?: string;
  readonly expected_after?: ExpectedVisualState;
  readonly idempotency_key: string;
  readonly retry_allowed: boolean;
}

export interface RecordingCue {
  readonly cue_id: string;
  readonly scene_id: string;
  readonly index: number;
  readonly title: string;
  readonly narration_ref?: string;
  readonly action_ids: readonly string[];
  readonly expected_state?: ExpectedVisualState;
  readonly recovery_hint?: string;
}

export interface RecordingScene {
  readonly scene_id: string;
  readonly index: number;
  readonly title: string;
  readonly narration_source: string; // episode_script ref
  readonly narration_text?: string;
  readonly cues: readonly RecordingCue[];
  readonly action_ids: readonly string[];
  readonly expected_result?: {
    readonly test?: 'PASS' | 'FAIL';
    readonly visual_state_id?: string;
  };
  readonly duration_sec: number;
}

export interface LiveExecutionPlan {
  readonly id: string; // plan_...
  readonly episode_id: string;
  readonly episode_revision_id: string;
  readonly preparation_revision: number;
  readonly plan_hash: string; // sha256 over canonical scenes+actions+payload_bundles
  readonly status: LiveExecutionPlanStatus;
  readonly created_at: string; // ISO
  readonly frozen_at?: string;
  readonly director_role: 'LIVE_DIRECTOR';
  readonly recording_profile: RecordingProfile;
  readonly scenes: readonly RecordingScene[];
  readonly actions: readonly PreparedAction[];
  /** Prepared payload bundles keyed by action_id — exact artifact content map (Section 6) */
  readonly payload_bundles?: Readonly<Record<string, string>>;
  readonly source_workspace_hash: string;
  readonly version: number;
}

export type RecordingProfile = {
  readonly resolution: '1920x1080' | '1280x720' | '3840x2160';
  readonly fps: 60 | 30;
  readonly codec: 'H264' | 'HEVC';
  readonly segment_minutes: 5 | 10;
  readonly audio_enabled: false; // P0: false per Principle F
};

// ─── Runtime lineage ─────────────────────────────────────────────────────────

export type LiveRecordSessionStatus =
  | 'IDLE'
  | 'PREPARING'
  | 'PREFLIGHT'
  | 'READY'
  | 'RECORDING'
  | 'PAUSED'
  | 'DIRECTOR_DEGRADED'
  | 'RECOVERING'
  | 'FINALIZING'
  | 'COMPLETED'
  | 'FAILED'
  | 'BLOCKED';

export interface DirectorSession {
  readonly session_id: string;
  readonly execution_plan_id: string;
  readonly execution_plan_hash: string;
  readonly provider_id: string;
  readonly model_id: string; // e.g. gemini-3.1-flash-live-preview
  readonly started_at: string;
  readonly expires_at: string;
}

export interface RecordingTake {
  readonly take_id: string;
  readonly execution_plan_id: string;
  readonly episode_id: string;
  readonly status: LiveRecordSessionStatus;
  readonly created_at: string;
  readonly segments: readonly RecordingSegment[];
}

export interface RecordingSegment {
  readonly segment_id: string;
  readonly take_id: string;
  readonly index: number;
  readonly file_path: string; // .../take_xxx/segment_xxx.mkv (no raw path exposure to UI)
  readonly started_at: string;
  readonly ended_at?: string;
  readonly duration_sec?: number;
  readonly is_playable: boolean;
}

export type RecordingEventType =
  | 'SESSION_START'
  | 'SESSION_END'
  | 'SCENE_START'
  | 'SCENE_END'
  | 'CUE_START'
  | 'CUE_END'
  | 'ACTION_START'
  | 'ACTION_SUCCESS'
  | 'ACTION_FAILURE'
  | 'NARRATION_CUE'
  | 'MARKER'
  | 'SEGMENT_START'
  | 'SEGMENT_END'
  | 'DIRECTOR_CONNECT'
  | 'DIRECTOR_DISCONNECT'
  | 'DIRECTOR_RESUME'
  | 'PAUSE'
  | 'RESUME';

export interface RecordingEvent {
  readonly t: number; // seconds since take start
  readonly type: RecordingEventType;
  readonly scene_id?: string;
  readonly cue_id?: string;
  readonly action_id?: string;
  readonly segment_id?: string;
  readonly execution_id?: string;
  readonly marker_type?: string;
  readonly detail?: string;
}

// ─── UI-facing projection (separate from domain mock) ────────────────────────

export interface SceneItem {
  readonly id: string;
  readonly index: number;
  readonly title: string;
  readonly duration: string; // hh:mm:ss
  readonly durationSec: number;
  readonly status: 'completed' | 'active' | 'pending';
  readonly script?: string;
  readonly scene_id?: string;
  readonly cue_id?: string;
}

export interface RecentRecording {
  readonly id: string;
  readonly title: string;
  readonly resolution: string;
  readonly fps: number;
  readonly format: string;
  readonly date: string;
  readonly time: string;
  readonly size: string;
  readonly duration: string;
  readonly thumbnailUrl?: string;
  readonly take_id?: string;
  readonly manifest_ref?: string;
}
