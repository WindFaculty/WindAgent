import { describe, it, expect } from 'vitest';
import { canTransition, evaluatePreflight, LIVE_RECORD_TRANSITIONS, isPlanFrozen, FAILURE_POLICIES } from '../domain/stateMachine';
import { checkPlanStaleness, isPlanHashWellFormed, validatePreparedAction, validateTimelineMonotonic } from '../domain/validation';
import { DIRECTOR_TOOL_DECLARATIONS, DIRECTOR_DENIED_TOOLS, isAllowedDirectorTool, validateDirectorToolCall } from '../contracts/directorTools';
import { DEFAULT_ENGINE_PROFILE, RECORDING_PERFORMANCE_GATES } from '../contracts/recordingEngine';
import type { PreparedAction, LiveExecutionPlan } from '../domain/types';

const ALL_GUARDS_PASS = {
  episodeRevisionOk: true,
  planFrozen: true,
  planStale: false,
  workspaceHashOk: true,
  artifactsPresent: true,
  actionsUntampered: true,
  providerResolved: true,
  credentialValid: true,
  liveConnectivityOk: true,
  recorderHealthy: true,
  wgcAvailable: true,
  nvencAvailable: true,
  diskSufficient: true,
  outputWritable: true,
  privacyScanPassed: true,
};

describe('P0 Frozen Contracts - Gate LIVE_RECORD_P0_ARCHITECTURE_FROZEN', () => {
  // -- State machine ---------------------------------------------------------
  it('state machine allows IDLE -> PREPARING but rejects IDLE -> RECORDING', () => {
    expect(canTransition('IDLE', 'PREPARING')).toBe(true);
    expect(canTransition('IDLE', 'RECORDING')).toBe(false);
  });

  it('state machine allows PREFLIGHT -> READY and READY -> RECORDING', () => {
    expect(canTransition('PREFLIGHT', 'READY')).toBe(true);
    expect(canTransition('READY', 'RECORDING')).toBe(true);
  });

  it('state machine rejects RECORDING -> IDLE (must go via FINALIZING)', () => {
    expect(canTransition('RECORDING', 'IDLE')).toBe(false);
    expect(canTransition('RECORDING', 'FINALIZING')).toBe(true);
  });

  it('all states have defined transitions', () => {
    for (const s of Object.keys(LIVE_RECORD_TRANSITIONS) as Array<keyof typeof LIVE_RECORD_TRANSITIONS>) {
      expect(Array.isArray(LIVE_RECORD_TRANSITIONS[s])).toBe(true);
    }
  });

  it('isPlanFrozen only true for FROZEN', () => {
    expect(isPlanFrozen('FROZEN')).toBe(true);
    expect(isPlanFrozen('DRAFT')).toBe(false);
    expect(isPlanFrozen('VALIDATED')).toBe(false);
    expect(isPlanFrozen('STALE')).toBe(false);
  });

  // -- Preflight guards ------------------------------------------------------
  it('preflight ok only when all guards pass', () => {
    const ok = evaluatePreflight(ALL_GUARDS_PASS);
    expect(ok.ok).toBe(true);
    expect(ok.blockers.length).toBe(0);
  });

  it('preflight blocks when plan not frozen and when stale', () => {
    const blocked = evaluatePreflight({ ...ALL_GUARDS_PASS, planFrozen: false, planStale: true });
    expect(blocked.ok).toBe(false);
    expect(blocked.blockers.some((b) => b.code === 'PLAN_NOT_FROZEN')).toBe(true);
    expect(blocked.blockers.some((b) => b.code === 'PLAN_STALE')).toBe(true);
  });

  it('preflight blocks on NVENC/WGC unavailability (fail-closed)', () => {
    const r = evaluatePreflight({ ...ALL_GUARDS_PASS, wgcAvailable: false, nvencAvailable: false });
    expect(r.blockers.some((b) => b.code === 'WGC_UNAVAILABLE')).toBe(true);
    expect(r.blockers.some((b) => b.code === 'NVENC_UNAVAILABLE')).toBe(true);
  });

  it('preflight fail-closed while privacy scan is pending or failed (Section 23/33)', () => {
    const pending = evaluatePreflight({ ...ALL_GUARDS_PASS, privacyScanPassed: undefined });
    expect(pending.ok).toBe(false);
    expect(pending.blockers.some((b) => b.code === 'PRIVACY_SCAN_FAILED')).toBe(true);

    const failed = evaluatePreflight({ ...ALL_GUARDS_PASS, privacyScanPassed: false });
    expect(failed.ok).toBe(false);
    expect(failed.blockers.some((b) => b.code === 'PRIVACY_SCAN_FAILED')).toBe(true);

    const passed = evaluatePreflight(ALL_GUARDS_PASS);
    expect(passed.blockers.some((b) => b.code === 'PRIVACY_SCAN_FAILED')).toBe(false);
  });

  it('failure policies cover all three classes', () => {
    const classes = new Set(FAILURE_POLICIES.map((p) => p.class));
    expect(classes.has('RECOVERABLE')).toBe(true);
    expect(classes.has('OPERATOR_REQUIRED')).toBe(true);
    expect(classes.has('FATAL')).toBe(true);
  });

  // -- Plan validation -------------------------------------------------------
  it('detects stale plan via episode_revision mismatch', () => {
    const plan = { episode_revision_id: 'rev_001' } as LiveExecutionPlan;
    expect(checkPlanStaleness(plan, 'rev_002').stale).toBe(true);
    expect(checkPlanStaleness(plan, 'rev_001').stale).toBe(false);
  });

  it('plan hash must be 64 hex chars', () => {
    expect(isPlanHashWellFormed('a'.repeat(64))).toBe(true);
    expect(isPlanHashWellFormed('abc')).toBe(false);
    expect(isPlanHashWellFormed('g'.repeat(64))).toBe(false);
  });

  it('prepared action requires artifact:// and idempotency_key', () => {
    const okAction: PreparedAction = {
      action_id: 'code_017',
      type: 'CODE_PLAYBACK',
      scene_id: 'scene-03',
      payload_ref: 'artifact://code/code_017',
      idempotency_key: 'idem_017',
      retry_allowed: false,
    };
    expect(validatePreparedAction(okAction, 'a'.repeat(64)).ok).toBe(true);

    const bad = { ...okAction, payload_ref: 'file:///tmp/code.py' } as PreparedAction;
    expect(validatePreparedAction(bad, 'a'.repeat(64)).ok).toBe(false);

    const noIdem = { ...okAction, idempotency_key: '' } as PreparedAction;
    expect(validatePreparedAction(noIdem, 'a'.repeat(64)).ok).toBe(false);
  });

  it('timeline must be monotonic', () => {
    expect(validateTimelineMonotonic([{ t: 0 }, { t: 1.2 }, { t: 1.2 }, { t: 5 }])).toBe(true);
    expect(validateTimelineMonotonic([{ t: 0 }, { t: 5 }, { t: 3 }])).toBe(false);
  });

  // -- Director tool manifest ------------------------------------------------
  it('director allowlist contains constrained tools only', () => {
    const names = DIRECTOR_TOOL_DECLARATIONS.map((d) => d.name);
    expect(names).toContain('execute_prepared_action');
    expect(names).toContain('advance_cue');
    expect(names).toContain('verify_visual_state');
    expect(names).not.toContain('write_file' as never);
    expect(names).not.toContain('shell' as never);
  });

  it('denylist contains shell/write_file/open_url/click', () => {
    expect(DIRECTOR_DENIED_TOOLS).toContain('shell');
    expect(DIRECTOR_DENIED_TOOLS).toContain('write_file');
    expect(DIRECTOR_DENIED_TOOLS).toContain('open_url');
    expect(DIRECTOR_DENIED_TOOLS).toContain('click');
  });

  it('isAllowedDirectorTool rejects denied tools', () => {
    expect(isAllowedDirectorTool('execute_prepared_action')).toBe(true);
    expect(isAllowedDirectorTool('shell')).toBe(false);
    expect(isAllowedDirectorTool('write_file')).toBe(false);
  });

  it('validateDirectorToolCall enforces action_id belongs to plan', () => {
    const allowed = new Set(['code_017', 'browser-002']);
    const states = new Set(['state_001']);
    const callOk = {
      tool: 'execute_prepared_action' as const,
      args: { action_id: 'code_017' },
      idempotency_key: 'idem',
      execution_id: 'exec_1',
    };
    expect(validateDirectorToolCall(callOk, allowed, states).ok).toBe(true);

    const callBad = { ...callOk, args: { action_id: 'evil_999' } };
    expect(validateDirectorToolCall(callBad, allowed, states).ok).toBe(false);
    expect(validateDirectorToolCall(callBad, allowed, states).reason).toBe('ACTION_NOT_IN_PLAN');
  });

  // -- Recording engine ------------------------------------------------------
  it('engine defaults to 1920x1080@60 H264 segmented MKV, audio disabled', () => {
    expect(DEFAULT_ENGINE_PROFILE.resolution).toEqual({ width: 1920, height: 1080 });
    expect(DEFAULT_ENGINE_PROFILE.fps).toBe(60);
    expect(DEFAULT_ENGINE_PROFILE.codec).toBe('H264');
    expect(DEFAULT_ENGINE_PROFILE.muxer).toBe('MKV_SEGMENTED');
    expect(DEFAULT_ENGINE_PROFILE.audio_enabled).toBe(false);
  });

  it('performance gates frozen per spec', () => {
    expect(RECORDING_PERFORMANCE_GATES.dropped_frames_pct_max).toBe(0.1);
    expect(RECORDING_PERFORMANCE_GATES.preview_delay_ms_max).toBe(200);
    expect(RECORDING_PERFORMANCE_GATES.gemini_sample_fps_max).toBe(2);
    expect(RECORDING_PERFORMANCE_GATES.nvenc_required).toBe(true);
  });

  // -- Subsystem boundary evidence -------------------------------------------
  it('four subsystems are importable (no god file)', async () => {
    const domain = await import('../domain');
    const contracts = await import('../contracts');
    const directorTypes = await import('../live-director/types');
    expect(domain.canTransition).toBeDefined();
    expect(contracts.DIRECTOR_TOOL_DECLARATIONS).toBeDefined();
    expect(directorTypes.DEFAULT_FRAME_SAMPLER).toBeDefined();
  });
});
