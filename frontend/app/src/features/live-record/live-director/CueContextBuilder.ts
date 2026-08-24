/**
 * CueContextBuilder — Phase 6 (ban_ke_hoach_v1.md Section 12)
 *
 * Gemini receives per-cycle context, NOT the whole Episode dump every frame:
 *
 * Session start:
 *   system instruction + frozen plan summary + allowed tools + current scene
 * Each cycle:
 *   current cue + expected state + latest screen frame + last tool result + elapsed
 *
 * The loop: Observe → Compare with expected state → Select approved action
 *           → Execute → Observe (Section 12).
 */

import type { LiveDirectorContext } from './types';
import type { LiveExecutionPlan } from '../domain/types';

export interface CueRef {
  readonly scene_id: string;
  readonly cue_id: string;
  readonly expected_state_id?: string;
}

export class CueContextBuilder {
  constructor(private readonly plan: LiveExecutionPlan) {}

  /** One-time system instruction assembled at session start. */
  buildSystemInstruction(): string {
    return [
      'You are LIVE_DIRECTOR — a constrained production recording agent.',
      'You observe screen frames and select the NEXT approved prepared action only.',
      'Never invent new actions, URLs, commands or code. If blocked, request_operator.',
      `Plan ${this.plan.id} (hash ${this.plan.plan_hash.slice(0, 12)}…) has ${this.plan.scenes.length} scenes and ${this.plan.actions.length} prepared actions.`,
      `Episode ${this.plan.episode_id} rev ${this.plan.episode_revision_id}.`,
      'Two pipelines: Recording @60FPS is independent — you only see 1–2 FPS downscaled frames.',
    ].join('\n');
  }

  /** Compact plan summary for the session-start packet (not full artifact dump). */
  buildPlanSummary(): string {
    const scenes = this.plan.scenes.map((s) => `${s.scene_id}: ${s.title} (${s.cues.length} cues)`).join('; ');
    const actions = this.plan.actions.map((a) => `${a.action_id}[${a.type}]`).join(', ');
    return `Scenes: [${scenes}] | Actions: [${actions}] | Profile: ${this.plan.recording_profile.resolution}@${this.plan.recording_profile.fps}`;
  }

  buildContext(params: {
    current: CueRef;
    lastToolResult?: unknown;
    elapsedSec: number;
    allowedTools: readonly string[];
  }): LiveDirectorContext {
    return {
      system_instruction: this.buildSystemInstruction(),
      frozen_plan_summary: this.buildPlanSummary(),
      allowed_tools: params.allowedTools,
      current_scene_id: params.current.scene_id,
      current_cue_id: params.current.cue_id,
      expected_state_id: params.current.expected_state_id,
      last_tool_result: params.lastToolResult,
      elapsed_sec: params.elapsedSec,
    };
  }
}
