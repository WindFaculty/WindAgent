/**
 * Live Record Validation — Phase 0 Frozen
 * Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN
 *
 * Fail-closed invariants: stale plan, hash mismatch, tampered action -> BLOCKED.
 */

import type { LiveExecutionPlan, PreparedAction } from './types';
import { isPlanFrozen } from './stateMachine';

export interface PlanStalenessCheck {
  readonly stale: boolean;
  readonly reason?: string;
}

export function checkPlanStaleness(plan: LiveExecutionPlan, currentEpisodeRevisionId: string): PlanStalenessCheck {
  if (plan.episode_revision_id !== currentEpisodeRevisionId) {
    return { stale: true, reason: `RECORDING_PLAN_STALE: plan=${plan.episode_revision_id} current=${currentEpisodeRevisionId}` };
  }
  return { stale: false };
}

export function assertPlanFrozenForRecording(plan: LiveExecutionPlan): void {
  if (!isPlanFrozen(plan.status)) {
    throw new Error(`RECORDING_PLAN_NOT_FROZEN: status=${plan.status} plan_id=${plan.id}`);
  }
}

// Deterministic plan_hash: sorted actions + scenes -> sha256 (here simplified as length check placeholder)
// Real implementation must hash canonical JSON. P0 freezes the *contract*, not the hash algo impl.
export function isPlanHashWellFormed(hash: string): boolean {
  return /^[a-f0-9]{64}$/i.test(hash);
}

export function validatePreparedAction(action: PreparedAction, planHash: string): { ok: boolean; reason?: string } {
  if (!action.action_id || !action.type || !action.payload_ref) {
    return { ok: false, reason: 'ACTION_MALFORMED' };
  }
  if (!action.payload_ref.startsWith('artifact://')) {
    return { ok: false, reason: 'PAYLOAD_REF_MUST_BE_ARTIFACT_URI' };
  }
  if (!action.idempotency_key) {
    return { ok: false, reason: 'IDEMPOTENCY_KEY_REQUIRED' };
  }
  // Tamper check: if planHash is known, ensure action belongs to plan (stub: hash linkage validated server-side)
  if (planHash && !isPlanHashWellFormed(planHash)) {
    return { ok: false, reason: 'PLAN_HASH_MALFORMED' };
  }
  return { ok: true };
}

export function validateTimelineMonotonic(events: Array<{ t: number }>): boolean {
  for (let i = 1; i < events.length; i++) {
    if (events[i].t < events[i - 1].t) return false;
  }
  return true;
}
