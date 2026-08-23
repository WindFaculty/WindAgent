/**
 * Live Record State Machine — Phase 0 Frozen
 * Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN
 *
 * Fail-closed: any blocker in PREFLIGHT prevents READY.
 * Recording engine lifecycle is independent from Gemini Live session (Principle D).
 */

import type { LiveRecordSessionStatus, LiveExecutionPlanStatus } from './types';

export type LiveRecordState = LiveRecordSessionStatus;

export const LIVE_RECORD_STATES: readonly LiveRecordState[] = [
  'IDLE',
  'PREPARING',
  'PREFLIGHT',
  'READY',
  'RECORDING',
  'PAUSED',
  'DIRECTOR_DEGRADED',
  'RECOVERING',
  'FINALIZING',
  'COMPLETED',
  'FAILED',
  'BLOCKED',
] as const;

// Allowed transitions — deterministic. No wildcard jumps.
export const LIVE_RECORD_TRANSITIONS: Readonly<Record<LiveRecordState, readonly LiveRecordState[]>> = {
  IDLE: ['PREPARING'],
  PREPARING: ['PREFLIGHT', 'FAILED', 'BLOCKED'],
  PREFLIGHT: ['READY', 'BLOCKED', 'FAILED'],
  READY: ['RECORDING', 'BLOCKED', 'FAILED'],
  RECORDING: ['PAUSED', 'DIRECTOR_DEGRADED', 'RECOVERING', 'FINALIZING', 'FAILED'],
  PAUSED: ['RECORDING', 'FINALIZING', 'FAILED'],
  DIRECTOR_DEGRADED: ['RECOVERING', 'PAUSED', 'FINALIZING', 'FAILED'],
  RECOVERING: ['RECORDING', 'DIRECTOR_DEGRADED', 'PAUSED', 'FAILED'],
  FINALIZING: ['COMPLETED', 'FAILED'],
  COMPLETED: ['IDLE'],
  FAILED: ['IDLE', 'PREPARING'],
  BLOCKED: ['PREPARING', 'IDLE'],
};

export function canTransition(from: LiveRecordState, to: LiveRecordState): boolean {
  const allowed = LIVE_RECORD_TRANSITIONS[from];
  return allowed ? (allowed as readonly string[]).includes(to) : false;
}

export function assertTransition(from: LiveRecordState, to: LiveRecordState): void {
  if (!canTransition(from, to)) {
    throw new Error(`LIVE_RECORD_STATE_TRANSITION_REJECTED: ${from} -> ${to} not allowed`);
  }
}

// ─── Plan status transitions (immutable after FROZEN) ────────────────────────

export const PLAN_STATUS_ORDER: Record<LiveExecutionPlanStatus, number> = {
  DRAFT: 0,
  PREPARED: 1,
  VALIDATED: 2,
  FROZEN: 3,
  STALE: 99,
  INVALID: 100,
};

export function isPlanFrozen(status: LiveExecutionPlanStatus): boolean {
  return status === 'FROZEN';
}

export function isPlanUsableForRecording(status: LiveExecutionPlanStatus): boolean {
  return status === 'FROZEN';
}

// ─── Preflight blockers — must ALL pass to reach READY ───────────────────────

export type PreflightBlockerCode =
  | 'PLAN_NOT_FROZEN'
  | 'PLAN_STALE'
  | 'WORKSPACE_HASH_MISMATCH'
  | 'ARTIFACT_MISSING'
  | 'PROVIDER_UNAVAILABLE'
  | 'MODEL_CAPABILITY_MISSING'
  | 'CREDENTIAL_INVALID'
  | 'LIVE_CONNECTIVITY_FAILED'
  | 'RECORDER_SIDECAR_UNHEALTHY'
  | 'WGC_UNAVAILABLE'
  | 'NVENC_UNAVAILABLE'
  | 'DISK_INSUFFICIENT'
  | 'OUTPUT_PATH_NOT_WRITABLE'
  | 'ACTION_TAMPERED';

export interface PreflightBlocker {
  readonly code: PreflightBlockerCode;
  readonly message: string;
  readonly recoverable: boolean;
}

export interface PreflightResult {
  readonly ok: boolean;
  readonly blockers: readonly PreflightBlocker[];
  readonly plan_hash?: string;
  readonly workspace_hash?: string;
}

export function evaluatePreflight(checks: {
  episodeRevisionOk: boolean;
  planFrozen: boolean;
  planStale: boolean;
  workspaceHashOk: boolean;
  artifactsPresent: boolean;
  actionsUntampered: boolean;
  providerResolved: boolean;
  credentialValid: boolean;
  liveConnectivityOk: boolean;
  recorderHealthy: boolean;
  wgcAvailable: boolean;
  nvencAvailable: boolean;
  diskSufficient: boolean;
  outputWritable: boolean;
}): PreflightResult {
  const blockers: PreflightBlocker[] = [];

  if (!checks.planFrozen) blockers.push({ code: 'PLAN_NOT_FROZEN', message: 'Execution plan chưa FROZEN', recoverable: true });
  if (checks.planStale) blockers.push({ code: 'PLAN_STALE', message: 'Episode revision != execution_plan.episode_revision', recoverable: false });
  if (!checks.workspaceHashOk) blockers.push({ code: 'WORKSPACE_HASH_MISMATCH', message: 'Source workspace hash mismatch', recoverable: false });
  if (!checks.artifactsPresent) blockers.push({ code: 'ARTIFACT_MISSING', message: 'Thiếu prepared artifact', recoverable: true });
  if (!checks.actionsUntampered) blockers.push({ code: 'ACTION_TAMPERED', message: 'Prepared action hash không khớp plan_hash', recoverable: false });
  if (!checks.providerResolved) blockers.push({ code: 'PROVIDER_UNAVAILABLE', message: 'Không resolve được LIVE_DIRECTOR provider', recoverable: true });
  if (!checks.credentialValid) blockers.push({ code: 'CREDENTIAL_INVALID', message: 'Provider credential invalid', recoverable: true });
  if (!checks.liveConnectivityOk) blockers.push({ code: 'LIVE_CONNECTIVITY_FAILED', message: 'Không kết nối được Gemini Live', recoverable: true });
  if (!checks.recorderHealthy) blockers.push({ code: 'RECORDER_SIDECAR_UNHEALTHY', message: 'Recorder sidecar không healthy', recoverable: true });
  if (!checks.wgcAvailable) blockers.push({ code: 'WGC_UNAVAILABLE', message: 'Windows Graphics Capture unavailable', recoverable: false });
  if (!checks.nvencAvailable) blockers.push({ code: 'NVENC_UNAVAILABLE', message: 'NVENC unavailable', recoverable: false });
  if (!checks.diskSufficient) blockers.push({ code: 'DISK_INSUFFICIENT', message: 'Không đủ dung lượng đĩa', recoverable: true });
  if (!checks.outputWritable) blockers.push({ code: 'OUTPUT_PATH_NOT_WRITABLE', message: 'Output path không ghi được', recoverable: true });
  if (!checks.episodeRevisionOk) blockers.push({ code: 'PLAN_STALE', message: 'Episode revision mismatch', recoverable: false });

  return { ok: blockers.length === 0, blockers };
}

// ─── Failure classification ───────────────────────────────────────────────────

export type FailureClass = 'RECOVERABLE' | 'OPERATOR_REQUIRED' | 'FATAL';

export interface FailurePolicy {
  readonly failure: string;
  readonly class: FailureClass;
  readonly action: 'RETRY_RESUME' | 'PAUSE_REQUEST_OPERATOR' | 'STOP_FINALIZE';
}

export const FAILURE_POLICIES: readonly FailurePolicy[] = [
  { failure: 'Gemini network disconnect', class: 'RECOVERABLE', action: 'RETRY_RESUME' },
  { failure: 'Browser page slow', class: 'RECOVERABLE', action: 'RETRY_RESUME' },
  { failure: 'Visual verification timeout', class: 'RECOVERABLE', action: 'RETRY_RESUME' },
  { failure: 'Tool command timeout', class: 'RECOVERABLE', action: 'RETRY_RESUME' },
  { failure: 'UI changed', class: 'OPERATOR_REQUIRED', action: 'PAUSE_REQUEST_OPERATOR' },
  { failure: 'VS Code unexpected dialog', class: 'OPERATOR_REQUIRED', action: 'PAUSE_REQUEST_OPERATOR' },
  { failure: 'Website requires login', class: 'OPERATOR_REQUIRED', action: 'PAUSE_REQUEST_OPERATOR' },
  { failure: 'disk full', class: 'FATAL', action: 'STOP_FINALIZE' },
  { failure: 'NVENC failure', class: 'FATAL', action: 'STOP_FINALIZE' },
  { failure: 'capture device destroyed', class: 'FATAL', action: 'STOP_FINALIZE' },
  { failure: 'plan tampered', class: 'FATAL', action: 'STOP_FINALIZE' },
  { failure: 'workspace hash mismatch', class: 'FATAL', action: 'STOP_FINALIZE' },
] as const;
