/**
 * useLiveDirector — Phase 6/10 cutover (ban_ke_hoach_v1.md Sections 11-12, 21)
 *
 * Wires the frozen LiveDirectorClient stack into React:
 *   bootstrapSession (ephemeral token, POST-only) → LiveDirectorClient →
 *   BidiGenerateContent WebSocket → gated tool dispatch → actionExecutor.
 *
 * Frames come from the sidecar's `recorder://preview` events (≤2 FPS JPEG
 * ≤1280×720, Principle E); this hook only re-stages them into the sampler
 * and drains it at the rate gate. The token is never persisted or logged —
 * it lives inside the client instance only.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { LiveExecutionPlan } from '../domain/types';
import type { RecorderPreviewFrame } from '../contracts/ipc';
import { LiveDirectorClient } from '../live-director/LiveDirectorClient';
import { createActionExecutor } from '../live-director/actionExecutor';
import type { LiveDirectorConnectionState } from '../live-director/types';
import { DIRECTOR_TOOL_DECLARATIONS } from '../contracts/directorTools';
import { defaultApiBaseUrl, useApiClient } from '../../../api/ApiProvider';
import { isTauriRuntime } from './useLiveRecorderSession';

export type DirectorPhase =
  | 'OFFLINE'
  | 'BOOTSTRAPPING'
  | 'CONNECTING'
  | 'LIVE'
  | 'DEGRADED'
  | 'FAILED';

export interface DirectorSnapshot {
  readonly connectionState: LiveDirectorConnectionState;
  readonly modelId: string | null;
  readonly sessionId: string | null;
  readonly currentSceneId: string;
  readonly currentCueId: string;
  readonly expectedStateId?: string;
  readonly latestModelTurn: string | null;
  readonly lastToolResult: unknown;
  readonly allowedTools: readonly string[];
}

const IDLE_SNAPSHOT: DirectorSnapshot = {
  connectionState: 'DISCONNECTED',
  modelId: null,
  sessionId: null,
  currentSceneId: '—',
  currentCueId: '—',
  expectedStateId: undefined,
  latestModelTurn: null,
  lastToolResult: undefined,
  allowedTools: [],
};

export interface UseLiveDirectorOptions {
  readonly plan: LiveExecutionPlan | null;
  /** Latest sidecar preview frame (already ≤1280×720 JPEG). */
  readonly previewFrame?: RecorderPreviewFrame | null;
  readonly takeId?: string | null;
  readonly onPauseRecording?: () => Promise<void> | void;
  readonly onResumeRecording?: () => Promise<void> | void;
  readonly onCreateMarker?: (markerType: string) => Promise<void> | void;
}

export interface UseLiveDirectorResult extends DirectorSnapshot {
  readonly phase: DirectorPhase;
  readonly error: string | null;
  connect(): Promise<void>;
  disconnect(): void;
}

/** Tauri invoke bound lazily so web/dev never pulls the desktop bridge. */
async function tauriInvoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  const mod = await import('@tauri-apps/api/core');
  return mod.invoke<T>(cmd, args);
}

export function useLiveDirector(opts: UseLiveDirectorOptions): UseLiveDirectorResult {
  const client = useApiClient();
  const [phase, setPhase] = useState<DirectorPhase>('OFFLINE');
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<DirectorSnapshot>(IDLE_SNAPSHOT);

  const directorRef = useRef<LiveDirectorClient | null>(null);
  const drainRef = useRef<number | null>(null);
  // Callbacks kept in a ref so the executor always sees the latest closures
  // without rebuilding the WebSocket stack mid-session.
  const cbRef = useRef(opts);
  cbRef.current = opts;

  // ── Frame staging: sidecar preview → sampler (rate-gated at send time) ──
  useEffect(() => {
    const frame = opts.previewFrame;
    const director = directorRef.current;
    if (!frame || !director) return;
    director.sampler.stageFromRecorderEvent(frame);
  }, [opts.previewFrame]);

  const pollSnapshot = useCallback(() => {
    const director = directorRef.current;
    if (!director) return;
    const s = director.session.snapshot();
    setSnapshot({
      connectionState: s.connectionState,
      modelId: s.model_id,
      sessionId: s.session_id,
      currentSceneId: s.currentSceneId,
      currentCueId: s.currentCueId,
      expectedStateId: s.expectedStateId,
      latestModelTurn: director.latestModelTurn,
      lastToolResult: s.lastToolResult,
      allowedTools: director.allowedToolNames,
    });
    setPhase((prev) => {
      if (prev === 'OFFLINE' || prev === 'BOOTSTRAPPING' || prev === 'FAILED') return prev;
      if (s.connectionState === 'CONNECTED') return 'LIVE';
      if (s.connectionState === 'RESUMING') return 'CONNECTING';
      if (s.connectionState === 'DEGRADED') return 'DEGRADED';
      return prev === 'CONNECTING' ? 'CONNECTING' : prev;
    });
  }, []);

  const connect = useCallback(async (): Promise<void> => {
    const plan = cbRef.current.plan;
    if (!plan) {
      setError('DIRECTOR_NO_PLAN: chưa có LiveExecutionPlan — hãy chuẩn bị ghi hình từ Episode trước.');
      setPhase('FAILED');
      return;
    }
    if (directorRef.current) return; // already connected/connecting

    setError(null);
    setPhase('BOOTSTRAPPING');
    try {
      const boot = (await client.liveRecord.bootstrapSession(
        { episode_id: plan.episode_id, execution_plan_id: plan.id },
        crypto.randomUUID(),
      )) as {
        session_id: string;
        provider_id: string;
        model_id: string;
        token: string;
        expires_at: string;
        execution_plan_hash: string;
      };

      const executor = createActionExecutor({
        plan,
        apiBaseUrl: defaultApiBaseUrl(),
        invokeTauri: isTauriRuntime() ? tauriInvoke : undefined,
        takeId: cbRef.current.takeId ?? undefined,
        onAdvanceCue: (cue) => {
          directorRef.current?.session.advanceTo(cue);
        },
        onPauseRecording: () => cbRef.current.onPauseRecording?.(),
        onResumeRecording: () => cbRef.current.onResumeRecording?.(),
        onCreateMarker: (markerType) => cbRef.current.onCreateMarker?.(markerType),
      });

      const director = new LiveDirectorClient({
        plan,
        config: {
          provider_id: boot.provider_id,
          model_id: boot.model_id,
          ephemeral_token: boot.token,
          expires_at: boot.expires_at,
          execution_plan_hash: boot.execution_plan_hash,
          session_id: boot.session_id,
        },
        executor,
        // §24/§35: reconnects after token expiry re-mint via the API before
        // resuming, so long takes never ride a dead ephemeral credential.
        refreshToken: async () => {
          try {
            const refreshed = (await client.liveRecord.refreshSessionToken(
              boot.session_id,
              crypto.randomUUID(),
            )) as { token?: string };
            return typeof refreshed.token === 'string' ? refreshed.token : null;
          } catch {
            return null; // non-fatal — resume proceeds with the current token
          }
        },
      });
      director.connect();
      directorRef.current = director;
      setPhase('CONNECTING');
      pollSnapshot();

      // Drain staged frames into the socket + refresh the panel snapshot.
      if (drainRef.current === null) {
        drainRef.current = window.setInterval(() => {
          const d = directorRef.current;
          if (!d) return;
          d.sendFrame();
          pollSnapshot();
        }, 500);
      }
    } catch (e) {
      directorRef.current = null;
      setError(e instanceof Error ? e.message : String(e));
      setPhase('FAILED');
    }
  }, [client, pollSnapshot]);

  const disconnect = useCallback((): void => {
    if (drainRef.current !== null) {
      clearInterval(drainRef.current);
      drainRef.current = null;
    }
    directorRef.current?.disconnect();
    directorRef.current = null;
    setPhase('OFFLINE');
    setSnapshot(IDLE_SNAPSHOT);
  }, []);

  // Tear down on unmount.
  useEffect(
    () => () => {
      if (drainRef.current !== null) clearInterval(drainRef.current);
      directorRef.current?.disconnect();
      directorRef.current = null;
    },
    [],
  );

  return { ...snapshot, allowedTools: DIRECTOR_TOOL_DECLARATIONS.map((d) => d.name), phase, error, connect, disconnect };
}
