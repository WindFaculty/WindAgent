/**
 * Live Director — Phase 0 Frozen
 * Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN
 *
 * Desktop TypeScript owns the Live WebSocket client (Desktop -> Gemini direct via ephemeral token).
 * Backend only issues ephemeral tokens; it never proxies the Live session.
 * Two pipelines: Recording @60FPS vs AI observation @1-2 FPS (downscaled 1280x720 JPEG/WebP).
 */

export type LiveDirectorConnectionState = 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED' | 'DEGRADED' | 'RESUMING';

export interface LiveDirectorClientConfig {
  readonly provider_id: string;
  readonly model_id: string; // gemini-3.1-flash-live-preview (UI shows Gemini 3 Flash Live)
  readonly ephemeral_token: string; // never persisted, never logged
  readonly expires_at: string;
  readonly execution_plan_hash: string;
  readonly session_id: string;
}

export interface LiveDirectorContext {
  readonly system_instruction: string;
  readonly frozen_plan_summary: string;
  readonly allowed_tools: readonly string[];
  readonly current_scene_id: string;
  readonly current_cue_id: string;
  readonly expected_state_id?: string;
  readonly last_tool_result?: unknown;
  readonly elapsed_sec: number;
}

export interface FrameSamplerConfig {
  readonly mode: 'event-driven' | 'periodic';
  readonly fps: 1 | 2;
  readonly downscale: { readonly width: 1280; readonly height: 720 };
  readonly format: 'JPEG' | 'WebP';
}

export const DEFAULT_FRAME_SAMPLER: FrameSamplerConfig = {
  mode: 'event-driven',
  fps: 1,
  downscale: { width: 1280, height: 720 },
  format: 'JPEG',
};

export interface SessionResumptionPolicy {
  readonly enabled: true;
  readonly max_attempts: number;
  readonly backoff_ms: number;
  readonly retain_cue: true;
  readonly no_replay_of_success: true;
}

export const DEFAULT_RESUMPTION_POLICY: SessionResumptionPolicy = {
  enabled: true,
  max_attempts: 5,
  backoff_ms: 1000,
  retain_cue: true,
  no_replay_of_success: true,
};
