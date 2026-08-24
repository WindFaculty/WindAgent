/**
 * LiveDirectorSession — Phase 6 (ban_ke_hoach_v1.md Section 11,12)
 *
 * Owns one Gemini Live WebSocket session's state machine within a RecordingTake.
 * Kept separate from LiveDirectorClient (transport) so session semantics
 * (cue tracking, last tool result, elapsed time) survive reconnects.
 */

import type { LiveDirectorClientConfig, LiveDirectorConnectionState } from './types';

export interface SessionSnapshot {
  readonly session_id: string;
  readonly execution_plan_id: string;
  readonly execution_plan_hash: string;
  readonly provider_id: string;
  readonly model_id: string;
  readonly connectionState: LiveDirectorConnectionState;
  readonly currentSceneId: string;
  readonly currentCueId: string;
  readonly expectedStateId?: string;
  readonly elapsedSec: number;
  readonly lastToolResult?: unknown;
}

export class LiveDirectorSession {
  private connectionState: LiveDirectorConnectionState = 'DISCONNECTED';
  private currentSceneId: string;
  private currentCueId: string;
  private expectedStateId?: string;
  private startedAtMs: number | null = null;
  private lastToolResult: unknown = undefined;

  constructor(
    readonly config: LiveDirectorClientConfig,
    initial: { scene_id: string; cue_id: string; expected_state_id?: string },
  ) {
    this.currentSceneId = initial.scene_id;
    this.currentCueId = initial.cue_id;
    this.expectedStateId = initial.expected_state_id;
  }

  get state(): LiveDirectorConnectionState { return this.connectionState; }
  setState(s: LiveDirectorConnectionState) { this.connectionState = s; }

  get current() { return { scene_id: this.currentSceneId, cue_id: this.currentCueId, expected_state_id: this.expectedStateId }; }

  advanceTo(cue: { cue_id: string; scene_id: string; expected_state_id?: string }): void {
    this.currentCueId = cue.cue_id;
    this.currentSceneId = cue.scene_id;
    this.expectedStateId = cue.expected_state_id;
  }

  setToolResult(result: unknown): void { this.lastToolResult = result; }

  markStarted(nowMs = Date.now()): void { this.startedAtMs = nowMs; this.connectionState = 'CONNECTED'; }

  get elapsedSec(): number {
    if (this.startedAtMs === null) return 0;
    return (Date.now() - this.startedAtMs) / 1000;
  }

  get expiresAt(): string { return this.config.expires_at; }

  snapshot(): SessionSnapshot {
    return {
      session_id: this.config.session_id,
      execution_plan_id: this.config.session_id, // hashed via config
      execution_plan_hash: this.config.execution_plan_hash,
      provider_id: this.config.provider_id,
      model_id: this.config.model_id,
      connectionState: this.connectionState,
      currentSceneId: this.currentSceneId,
      currentCueId: this.currentCueId,
      expectedStateId: this.expectedStateId,
      elapsedSec: this.elapsedSec,
      lastToolResult: this.lastToolResult,
    };
  }
}
