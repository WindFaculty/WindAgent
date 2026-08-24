/**
 * Live Record V3 API contracts (live_record.contract/v0.1).
 *
 * Python mirror: core/windagent_core/domain/live_record + routers/v3/live_record.
 * The plan is immutable after FROZEN; only FROZEN plans open recording takes
 * (ban_ke_hoach_v1.md Phase 1). Domain-level TS types live in the frozen
 * Phase-0 feature contracts (features/live-record/domain/types.ts); these are
 * the wire shapes for /api/v3/live-record/*.
 */

// ── Plan lifecycle ─────────────────────────────────────────────────────────

export type LiveExecutionPlanStatus =
  | 'DRAFT'
  | 'PREPARED'
  | 'VALIDATED'
  | 'FROZEN'
  | 'STALE'
  | 'INVALID';

/** Wire shape of GET/POST /api/v3/live-record/plans (snake_case JSON). */
export interface LiveExecutionPlanResource {
  plan_id: string;
  episode_id: string;
  episode_revision_id: string;
  preparation_revision: number;
  plan_hash: string;
  status: LiveExecutionPlanStatus;
  director_role: 'LIVE_DIRECTOR';
  recording_profile: {
    resolution: '1920x1080' | '1280x720' | '3840x2160';
    fps: 30 | 60;
    codec: 'H264' | 'HEVC';
    segment_minutes: 5 | 10;
    audio_enabled: false; // Principle F — locked OFF at the type level
  };
  scenes: unknown[];
  actions: unknown[];
  source_workspace_hash: string;
  created_at: string;
  frozen_at: string | null;
  optimistic_version: number;
  recordable: boolean;
}

export interface LiveExecutionPlanListResponse {
  items: LiveExecutionPlanResource[];
}

export interface CreateLivePlanRequest {
  episode_id: string;
  episode_revision_id: string;
  scenes?: unknown[];
  actions?: unknown[];
  recording_profile?: Record<string, unknown>;
  /** Prepared payload bundles keyed by action_id — exact artifact content map (Section 6) */
  payload_bundles?: Record<string, string>;
}

export interface PatchLivePlanContentRequest {
  scenes?: unknown[];
  actions?: unknown[];
  payload_bundles?: Record<string, string>;
  source_workspace_hash?: string;
}

export interface StalenessCheckRequest {
  current_episode_revision_id: string;
}

// ── Takes & timeline ───────────────────────────────────────────────────────

/** Mirrors LiveRecordSessionStatus (12 states) from the Phase-0 domain types. */
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

export interface RecordingTakeResource {
  take_id: string;
  execution_plan_id: string;
  /** Canonical plan hash stamped when the take opened (tamper evidence). */
  execution_plan_hash: string;
  episode_id: string;
  session_status: LiveRecordSessionStatus;
  started_at: string | null;
  ended_at: string | null;
  optimistic_version: number;
  metadata: Record<string, unknown>;
}

export interface RecordingTakeListResponse {
  items: RecordingTakeResource[];
}

export interface AppendTakeEventRequest {
  event_type: string;
  t?: number;
  scene_id?: string | null;
  cue_id?: string | null;
  action_id?: string | null;
  segment_id?: string | null;
  execution_id?: string | null;
  marker_type?: string | null;
  detail?: string;
  payload?: Record<string, unknown>;
}

export interface RecordingEventResource extends AppendTakeEventRequest {
  take_id: string;
  /** Per-take monotonic sequence assigned by the repository on append. */
  seq: number;
}

export interface RecordingEventListResponse {
  items: RecordingEventResource[];
}

// ── Director session bootstrap (Phase 5) ─────────────────────────────────────

export interface BootstrapDirectorSessionRequest {
  episode_id: string;
  execution_plan_id: string;
  current_episode_revision_id?: string | null;
}

export interface BootstrapDirectorSessionResponse {
  session_id: string;
  provider_id: string;
  /** Wire model ID — e.g. gemini-3.1-flash-live-preview (UI shows "Gemini 3 Flash Live") */
  model_id: string;
  /** Ephemeral token — never persisted, never logged, never returned via GET */
  token: string;
  expires_at: string;
  execution_plan_hash: string;
  display_name: string;
}

export interface DirectorSessionResource {
  session_id: string;
  execution_plan_id: string;
  execution_plan_hash: string;
  provider_id: string | null;
  model_id: string | null;
  connection_state: string;
  started_at: string;
  expires_at: string | null;
  metadata: Record<string, unknown>;
  has_token: boolean;
}

// ── Recording Preparation (Phase 2) ───────────────────────────────────────

export interface PrepareRecordingRequest {
  episode_id: string;
  episode_revision_id: string;
  source_workspace_hash?: string;
  recording_profile?: Record<string, unknown>;
  scenes: {
    title: string;
    narration_source?: string;
    narration_text?: string;
    duration_sec?: number;
    expected_result?: Record<string, unknown>;
    actions: {
      type: string;
      file?: string;
      target_file?: string;
      content?: string;
      payload?: string;
      command?: string;
      typing_mode?: 'TYPE' | 'PASTE';
      chars_per_second?: number;
      browser_semantic_target?: string;
      semantic_text?: string;
      expected_after?: Record<string, unknown>;
      retry_allowed?: boolean;
    }[];
  }[];
  plan_id?: string;
}
