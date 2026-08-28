/**
 * useLiveRecordingController — Phase 14/15/16 application orchestration layer
 * (ban_ke_hoach_v1.md §18-§20).
 *
 *   LiveRecordPage
 *        ↓
 *   useLiveRecordingController
 *        ├── useLiveRecorderSession   probe · prepare · start · pause · resume ·
 *        │                            stop · marker · recover (frozen IPC surface)
 *        ├── useLiveDirector          Gemini Live lifecycle (§20)
 *        ├── useLiveDirectorPlan      frozen plan loader
 *        ├── preflight                §23 guards from real probes — non-optimistic
 *        └── Take API                 lineage: createTake → segment relay
 *
 * §18 mandate: `useLiveRecord` no longer supplies production metrics. Every
 * counter this controller exposes comes from the engine's own status payload;
 * anything the engine has not measured yet surfaces as `null` so the UI renders
 * an honest "—" instead of a hardcoded number. The legacy mock store is ONLY
 * consulted when there is no Tauri runtime at all (web dev preview) and never
 * inside the desktop shell.
 *
 * Start flow (§20, frozen order):
 *   Create Take → Prepare native recorder → Bootstrap Gemini Live → Connect →
 *   Director READY → Start recorder. A director that drops AFTER start only
 *   degrades — the recording continues.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  CaptureSources,
  NativeCapabilities,
  RecorderSegmentEvent,
  RecorderStatus,
  RecorderPreviewFrame,
  AudioMeterEvent,
} from '../contracts/ipc';
import type { RecordingEngineProfile } from '../contracts/recordingEngine';
import { DEFAULT_ENGINE_PROFILE, ENGINE_CONTRACT_VERSION } from '../contracts/recordingEngine';
import type { LiveExecutionPlan, SceneItem } from '../domain/types';
import type { TimelineEntry } from './useLiveRecorderSession';
import { useLiveRecorderSession } from './useLiveRecorderSession';
import { useLiveDirector, type UseLiveDirectorResult } from './useLiveDirector';
import { useLiveDirectorPlan, type PlanLoadPhase } from './useLiveDirectorPlan';
import type { PreflightChecks } from '../components/PreflightChecklist';
import { formatDuration, useLiveRecord, type AudioLevels, type UseLiveRecordResult } from './useLiveRecord';
import { useApiClient } from '../../../api/ApiProvider';

/** §15: the FE refuses to talk to an engine speaking a different contract. */
function contractVersionMatches(caps: NativeCapabilities | null): boolean {
  return caps !== null && Number(caps.contract_version) === ENGINE_CONTRACT_VERSION;
}

/** How long Bootstrap→Connect may take before START is refused (§20). */
const DIRECTOR_READY_TIMEOUT_MS = 12_000;
const DIRECTOR_READY_POLL_MS = 250;

export interface LiveRecordingMetrics {
  readonly isRecording: boolean;
  readonly isPaused: boolean;
  readonly timeFormatted: string;
  readonly framesCaptured: number;
  readonly framesDropped: number;
  readonly droppedPct: string;
  /** null ⇒ not measured yet — renderers must show "—", never a guess. */
  readonly bitrateMbps: number | null;
  readonly captureFps: number | null;
  readonly encodeFps: number | null;
  readonly avSyncErrorMs: number | null;
  readonly resourceStage: string | null;
  readonly nvencStatus: string | null;
  readonly diskWriteMbps: number | null;
  readonly diskFreeGb: number | null;
  readonly gpuAdapterName: string | null;
}

const EMPTY_METRICS: LiveRecordingMetrics = {
  isRecording: false,
  isPaused: false,
  timeFormatted: formatDuration(0),
  framesCaptured: 0,
  framesDropped: 0,
  droppedPct: '0.00',
  bitrateMbps: null,
  captureFps: null,
  encodeFps: null,
  avSyncErrorMs: null,
  resourceStage: null,
  nvencStatus: null,
  diskWriteMbps: null,
  diskFreeGb: null,
  gpuAdapterName: null,
};

export interface UseLiveRecordingControllerResult {
  // Identity / transport
  readonly native: boolean;
  readonly busy: boolean;
  readonly startInFlight: boolean;
  readonly lastStartError: string | null;

  // Frozen plan loader
  readonly plan: LiveExecutionPlan | null;
  readonly planPhase: PlanLoadPhase;
  readonly planError: string | null;
  /** True when the frozen plan carries scenes (Principle A authority). */
  readonly planMode: boolean;
  readonly projectedScenes: readonly SceneItem[];
  readonly totalExpectedDurationFormatted: string;

  // Engine session passthrough (render-only data)
  readonly status: RecorderStatus | null;
  readonly capabilities: NativeCapabilities | null;
  readonly previewFrame: RecorderPreviewFrame | null;
  readonly segments: readonly RecorderSegmentEvent[];
  readonly audioMeter: AudioMeterEvent | null;
  readonly timeline: readonly TimelineEntry[];
  readonly warnings: readonly string[];
  readonly errors: readonly string[];
  dismissErrors(): void;

  // §17 settings surface
  readonly engineProfile: RecordingEngineProfile;
  setEngineProfile(next: RecordingEngineProfile): void;
  readonly captureSources: CaptureSources | null;

  // §23 preflight (non-optimistic)
  readonly preflightChecks: PreflightChecks;
  readonly allPreflightPass: boolean;

  // Director snapshot (§20)
  readonly director: UseLiveDirectorResult;

  // Metrics — engine-authoritative inside the desktop shell (§18)
  readonly metrics: LiveRecordingMetrics;
  readonly audioLevels: AudioLevels;

  /**
   * UI-only store (teleprompter, modals, demo scenes) — the SAME single
   * instance the controller reads its fallbacks from, so the page never spins
   * up a second diverging `useLiveRecord`.
   */
  readonly ui: UseLiveRecordResult;

  // Actions (the ONLY way the page mutates recording state)
  startTake(): Promise<void>;
  stopTake(): Promise<void>;
  pauseTake(): Promise<void>;
  resumeTake(): Promise<void>;
  createMarker(markerType: string): Promise<void>;
  toggleMicMute(): void;
  toggleSystemMute(): void;
}

export function useLiveRecordingController(): UseLiveRecordingControllerResult {
  const apiClient = useApiClient();
  const mock = useLiveRecord(); // web-dev demo store ONLY (never in the shell)
  const session = useLiveRecorderSession();
  const planLoader = useLiveDirectorPlan();
  const native = session.native;

  const plan = planLoader.plan;
  const planMode = (plan?.scenes ?? []).length > 0;
  const activeSceneIndex = mock.activeSceneIndex;

  // ── §17 settings state ──────────────────────────────────────────────────────
  const [engineProfile, setEngineProfile] = useState<RecordingEngineProfile>(DEFAULT_ENGINE_PROFILE);
  const [captureSources, setCaptureSources] = useState<CaptureSources | null>(null);
  const [startInFlight, setStartInFlight] = useState(false);
  const [lastStartError, setLastStartError] = useState<string | null>(null);

  const { getSources } = session;
  useEffect(() => {
    if (!native) return;
    let cancelled = false;
    void getSources().then((srcs) => {
      if (!cancelled && srcs) setCaptureSources(srcs);
    });
    return () => {
      cancelled = true;
    };
  }, [native, getSources]);

  // Frozen-plan intent seeds the editable profile once per plan load: codec /
  // fps / segment come from the FROZEN recording_profile; everything else keeps
  // quality-first defaults and stays user-editable afterwards.
  const seededPlanIdRef = useRef<string | null>(null);
  useEffect(() => {
    const pid = plan?.id ?? null;
    if (!pid || seededPlanIdRef.current === pid) return;
    seededPlanIdRef.current = pid;
    const pp = plan?.recording_profile as Record<string, unknown> | undefined;
    setEngineProfile((prev) => ({
      ...prev,
      video: {
        ...prev.video,
        codec: pp?.codec === 'HEVC' ? 'HEVC' : prev.video.codec,
        fps: pp?.fps === 30 ? 30 : prev.video.fps,
      },
      container: {
        ...prev.container,
        segment_minutes: pp?.segment_minutes === 10 ? 10 : prev.container.segment_minutes,
      },
    }));
  }, [plan]);

  // ── Take lineage: createTake before engine start → segments relay to DB ────
  const takeIdRef = useRef<string | null>(null);

  // Director needs live callbacks into the recorder; the controller owns both.
  const director = useLiveDirector({
    plan,
    previewFrame: session.previewFrame,
    takeId: takeIdRef.current,
    onPauseRecording: async () => { await session.pause(); },
    onResumeRecording: async () => { await session.resume(); },
    onCreateMarker: async (markerType) => { await session.createMarker({ marker_type: markerType }); },
  });
  // Latest director snapshot without stale-closure polls (§20 readiness gate).
  const directorRef = useRef(director);
  directorRef.current = director;

  // ── §23 privacy scan — once per loaded plan, fail-closed until PASS ────────
  const [privacyScan, setPrivacyScan] = useState<{ status: string } | null>(null);
  const scannedPlanIdRef = useRef<string | null>(null);
  useEffect(() => {
    const planId = planMode && plan ? plan.id : null;
    if (!planId || !native) return;
    if (scannedPlanIdRef.current === planId) return;
    scannedPlanIdRef.current = planId;
    setPrivacyScan(null);
    let cancelled = false;
    apiClient.liveRecord
      .runPrivacyScan(planId)
      .then((res) => {
        if (!cancelled) setPrivacyScan({ status: String(res['status'] ?? 'BLOCKED') });
      })
      .catch(() => {
        if (!cancelled) setPrivacyScan({ status: 'BLOCKED' }); // unavailable ⇒ fail-closed
      });
    return () => {
      cancelled = true;
    };
  }, [plan, planMode, native, apiClient]);

  // ── §23 preflight — non-optimistic: unknown ⇒ blocked, never assumed PASS ──
  const caps = session.capabilities;
  const rs = session.status;
  const blockerCodes = new Set<string>([
    ...((caps?.blockers as readonly string[] | undefined) ?? []),
    ...((rs?.blockers as readonly string[] | undefined) ?? []),
  ]);

  const preflightChecks: PreflightChecks = useMemo(
    () => ({
      episodeRevisionOk: !blockerCodes.has('PLAN_STALE'),
      planFrozen: !blockerCodes.has('PLAN_NOT_FROZEN'),
      planStale: blockerCodes.has('PLAN_STALE'),
      workspaceHashOk: !blockerCodes.has('WORKSPACE_HASH_MISMATCH'),
      artifactsPresent: !blockerCodes.has('ARTIFACT_MISSING'),
      actionsUntampered: !blockerCodes.has('ACTION_TAMPERED'),
      providerResolved: !blockerCodes.has('PROVIDER_UNAVAILABLE'),
      credentialValid: !blockerCodes.has('CREDENTIAL_INVALID'),
      liveConnectivityOk: !blockerCodes.has('LIVE_CONNECTIVITY_FAILED'),
      privacyScanPassed: native ? privacyScan?.status === 'PASS' : true,
      // Healthy requires one successful capability round-trip whose backend is
      // the real engine at OUR contract version — never an optimistic default.
      recorderHealthy:
        native &&
        caps !== null &&
        caps.engine_available &&
        caps.backend === 'wgc-nvenc-mkv' &&
        contractVersionMatches(caps),
      wgcAvailable: Boolean(caps?.wgc_available ?? false),
      nvencAvailable: Boolean(caps?.nvenc_available ?? false),
      diskSufficient: caps ? Number(caps.disk_free_gb) >= 2 : false,
      outputWritable: Boolean(caps?.output_writable ?? false),
    }),
    // blockerCodes is rebuilt each render from two arrays — key on the sorted join.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      blockerCodes.has('PLAN_STALE'),
      blockerCodes.has('PLAN_NOT_FROZEN'),
      blockerCodes.has('WORKSPACE_HASH_MISMATCH'),
      blockerCodes.has('ARTIFACT_MISSING'),
      blockerCodes.has('ACTION_TAMPERED'),
      blockerCodes.has('PROVIDER_UNAVAILABLE'),
      blockerCodes.has('CREDENTIAL_INVALID'),
      blockerCodes.has('LIVE_CONNECTIVITY_FAILED'),
      native,
      privacyScan?.status,
      caps,
    ],
  );

  // While the desktop shell has no capability snapshot yet (sidecar still
  // spawning), keep probing every few seconds instead of leaving the page dead.
  const refreshCapabilitiesRef = useRef(session.refreshCapabilities);
  refreshCapabilitiesRef.current = session.refreshCapabilities;
  useEffect(() => {
    if (!native || caps !== null) return;
    const interval = setInterval(() => void refreshCapabilitiesRef.current(), 3_000);
    return () => clearInterval(interval);
  }, [native, caps]);

  // Section 23: nút "Bắt đầu ghi" chỉ enable khi preflight PASS hết (native).
  const allPreflightPass = useMemo(() => {
    if (!native) return true; // web dev demo — no engine gates exist there
    const hard: readonly boolean[] = [
      preflightChecks.episodeRevisionOk,
      planMode ? plan?.status === 'FROZEN' : preflightChecks.planFrozen,
      preflightChecks.workspaceHashOk,
      preflightChecks.artifactsPresent,
      preflightChecks.actionsUntampered,
      preflightChecks.providerResolved,
      preflightChecks.credentialValid,
      preflightChecks.liveConnectivityOk,
      preflightChecks.privacyScanPassed === true, // absent ⇒ fail-closed (§23)
      preflightChecks.recorderHealthy,
      preflightChecks.wgcAvailable,
      preflightChecks.nvencAvailable,
      preflightChecks.diskSufficient,
      preflightChecks.outputWritable,
    ];
    return hard.every(Boolean);
  }, [native, preflightChecks, planMode, plan?.status]);

  // ── §18 metrics — engine-authoritative inside the shell ────────────────────
  const metrics: LiveRecordingMetrics = useMemo(() => {
    if (native) {
      if (rs === null) return EMPTY_METRICS; // honest zeros until the engine talks
      return {
        isRecording: rs.state === 'RECORDING',
        isPaused: rs.state === 'PAUSED',
        timeFormatted: formatDuration(rs.elapsed_sec),
        framesCaptured: rs.frames_captured,
        framesDropped: rs.frames_dropped,
        droppedPct: rs.dropped_pct.toFixed(2),
        bitrateMbps: rs.bitrate_mbps > 0 ? rs.bitrate_mbps : null,
        captureFps: rs.capture_fps ?? null,
        encodeFps: rs.encode_fps ?? null,
        avSyncErrorMs: rs.av_sync_error_ms ?? null,
        resourceStage: rs.resource_stage ?? null,
        nvencStatus: rs.nvenc_status ?? null,
        diskWriteMbps: rs.disk_write_mbps ?? null,
        diskFreeGb: caps ? Number(caps.disk_free_gb) : null,
        gpuAdapterName: caps?.gpu_adapter_name || null,
      };
    }
    // Web dev preview fallback — unreachable inside the Tauri shell by design.
    return {
      isRecording: mock.isRecording,
      isPaused: mock.isPaused,
      timeFormatted: mock.recordingTimeFormatted,
      framesCaptured: mock.recordedFrames,
      framesDropped: mock.droppedFrames,
      droppedPct: mock.droppedFramesPercent,
      bitrateMbps: mock.currentBitrate > 0 ? mock.currentBitrate : null,
      captureFps: null,
      encodeFps: null,
      avSyncErrorMs: null,
      resourceStage: null,
      nvencStatus: null,
      diskWriteMbps: null,
      diskFreeGb: null,
      gpuAdapterName: null,
    };
  }, [native, rs, caps, mock]);

  // ── §10/§11 audio meters — engine values win; voiceover stays UI-only ──────
  const micMeter = session.audioMeter?.track === 'mic' ? session.audioMeter : null;
  const systemMeter = session.audioMeter?.track === 'system' ? session.audioMeter : null;
  const audioLevels: AudioLevels = native
    ? {
        ...mock.audioLevels,
        mic: micMeter ? Math.round(micMeter.rms_dbfs) : -100,
        system: systemMeter ? Math.round(systemMeter.rms_dbfs) : -100,
      }
    : mock.audioLevels;

  const toggleMicMute = useCallback(() => {
    if (native) {
      void session.mute({
        mic_muted: !mock.audioLevels.isMicMuted,
        system_muted: mock.audioLevels.isSystemMuted,
      });
    }
    mock.toggleMicMute();
  }, [native, session, mock]);

  const toggleSystemMute = useCallback(() => {
    if (native) {
      void session.mute({
        mic_muted: mock.audioLevels.isMicMuted,
        system_muted: !mock.audioLevels.isSystemMuted,
      });
    }
    mock.toggleSystemMute();
  }, [native, session, mock]);

  // ── §20 Start flow: Take → Prepare → Director READY → Start ────────────────
  const startTake = useCallback(async (): Promise<void> => {
    if (!native) {
      mock.handleStartRecording(); // web dev demo only
      return;
    }
    if (startInFlight || metrics.isRecording) return;
    setStartInFlight(true);
    setLastStartError(null);
    try {
      // 1. Lineage: open the take in the API so segments/events have a home.
      if (plan && !takeIdRef.current) {
        try {
          const take = await apiClient.liveRecord.createTake(plan.id, {});
          const tid = String(take['take_id'] ?? take['id'] ?? '');
          if (tid) takeIdRef.current = tid;
        } catch {
          // API unavailable → engine mints its own take id; relay skips this run.
        }
      }

      // 2. Prepare the sidecar with the LIVE settings profile — exactly what
      //    DeviceSettingsPanel shows (§17); the engine validator stays authoritative.
      const prepared = (await session.prepare({
        execution_plan_id: plan?.id ?? 'adhoc',
        execution_plan_hash: plan?.plan_hash ?? '',
        episode_id: plan?.episode_id ?? '',
        output_dir: mock.savePath || 'recordings',
        profile: engineProfile,
      })) as { prepared?: boolean; blockers?: string[] } | null;
      if (prepared && prepared.prepared === false) return; // blockers surfaced via events

      // 3. §20 frozen order — Gemini Live connects BEFORE the recorder rolls.
      await directorRef.current.connect();
      const readyBy = Date.now() + DIRECTOR_READY_TIMEOUT_MS;
      let directorReady = false;
      while (Date.now() < readyBy) {
        if (directorRef.current.connectionState === 'CONNECTED') {
          directorReady = true;
          break;
        }
        if (directorRef.current.phase === 'FAILED') break;
        await new Promise((r) => setTimeout(r, DIRECTOR_READY_POLL_MS));
      }
      if (!directorReady) {
        // No READY ⇒ no recording. Tear the half-open session down and surface why.
        directorRef.current.disconnect();
        takeIdRef.current = null;
        setLastStartError(
          directorRef.current.error ??
            'DIRECTOR_NOT_READY: Gemini Live chưa sẵn sàng trước khi ghi — START bị từ chối.',
        );
        return;
      }

      // 4. Only now does the engine roll. After this point a director drop is
      //    DEGRADED — the recording continues regardless (§20).
      await session.start({
        execution_plan_id: plan?.id ?? 'adhoc',
        ...(takeIdRef.current ? { take_id: takeIdRef.current } : {}),
      });
    } finally {
      setStartInFlight(false);
    }
  }, [native, apiClient, plan, engineProfile, mock.savePath, session, metrics.isRecording, startInFlight, mock.handleStartRecording]);

  const stopTake = useCallback(async (): Promise<void> => {
    if (!native) {
      mock.handleStopRecording();
      return;
    }
    await session.stop();
    director.disconnect(); // §21: the director session ends with the take
    takeIdRef.current = null;
  }, [native, session, director, mock.handleStopRecording]);

  const pauseTake = useCallback(async (): Promise<void> => {
    if (!native) {
      mock.handlePauseRecording();
      return;
    }
    await session.pause();
  }, [native, session, mock.handlePauseRecording]);

  const resumeTake = useCallback(async (): Promise<void> => {
    if (!native) {
      mock.handlePauseRecording(); // mock store toggles pause/resume in one action
      return;
    }
    await session.resume();
  }, [native, session, mock.handlePauseRecording]);

  const createMarker = useCallback(
    async (markerType: string): Promise<void> => {
      if (!native) return;
      await session.createMarker({ marker_type: markerType });
    },
    [native, session],
  );

  // ── Plan projections for render-only panels ─────────────────────────────────
  const projectedScenes = useMemo(
    () => (planMode ? planLoader.projectSceneItems(activeSceneIndex) : mock.scenes),
    [planMode, planLoader, activeSceneIndex, mock.scenes],
  );

  return {
    native,
    busy: session.busy,
    startInFlight,
    lastStartError,

    plan,
    planPhase: planLoader.phase,
    planError: planLoader.error,
    planMode,
    projectedScenes,
    totalExpectedDurationFormatted: mock.totalExpectedDurationFormatted,

    status: rs,
    capabilities: caps,
    previewFrame: session.previewFrame,
    segments: session.segments,
    audioMeter: session.audioMeter,
    timeline: session.timeline,
    warnings: session.warnings,
    errors: [...session.errors, ...(lastStartError ? [lastStartError] : [])],
    dismissErrors: session.dismissErrors,

    engineProfile,
    setEngineProfile,
    captureSources,

    preflightChecks,
    allPreflightPass,

    director,

    metrics,
    audioLevels,
    ui: mock,

    startTake,
    stopTake,
    pauseTake,
    resumeTake,
    createMarker,
    toggleMicMute,
    toggleSystemMute,
  };
}
