/**
 * useLiveRecorderSession — Phase E cutover (ban_ke_hoach_v1.md Section 9-11)
 *
 * Real-state replacement for the mock clock in `useLiveRecord`. Binds the
 * frozen Tauri surface:
 *   commands: recorder_prepare|start|pause|resume|stop|create_marker|
 *             get_status|get_capabilities
 *   events:   recorder://status|segment|preview|warning|error|timeline
 *
 * On the web (no Tauri runtime) every command resolves to null and the page
 * keeps rendering via the legacy mock hook — dev fallback stays intact.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  NativeCapabilities,
  RecorderCommand,
  RecorderPrepareRequest,
  RecorderPreviewFrame,
  RecorderSegmentEvent,
  RecorderStatus,
  RecorderStartRequest,
  MarkerRequest,
} from '../contracts/ipc';
import { isRecorderStatus } from '../contracts/ipc';

/** True inside the Tauri desktop shell (v2 exposes __TAURI_INTERNALS__). */
export function isTauriRuntime(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

export interface TimelineEntry {
  readonly t: number;
  readonly type: string;
  readonly detail?: string;
}

export interface RecorderSessionState {
  readonly status: RecorderStatus | null;
  /** Raw last status payload — survives contract drift without crashing UI. */
  readonly statusRaw: Record<string, unknown> | null;
  readonly capabilities: NativeCapabilities | null;
  readonly previewFrame: RecorderPreviewFrame | null;
  readonly segments: readonly RecorderSegmentEvent[];
  readonly timeline: readonly TimelineEntry[];
  readonly warnings: readonly string[];
  readonly errors: readonly string[];
}

export interface UseLiveRecorderSessionResult extends RecorderSessionState {
  readonly native: boolean;
  readonly busy: boolean;
  prepare(request: RecorderPrepareRequest): Promise<Record<string, unknown> | null>;
  start(request: RecorderStartRequest): Promise<Record<string, unknown> | null>;
  pause(): Promise<Record<string, unknown> | null>;
  resume(): Promise<Record<string, unknown> | null>;
  stop(): Promise<Record<string, unknown> | null>;
  createMarker(request: MarkerRequest): Promise<string | null>;
  refreshStatus(): Promise<void>;
  refreshCapabilities(): Promise<void>;
  dismissErrors(): void;
}

const MAX_LOG_LINES = 200;

function pushBounded(list: string[], line: string): string[] {
  const next = [...list, line];
  return next.length > MAX_LOG_LINES ? next.slice(next.length - MAX_LOG_LINES) : next;
}

export interface UseLiveRecorderSessionOptions {
  /** Relay hook for finalized MKV segments (engine → host → DB lineage). */
  readonly onSegmentEvent?: (segment: RecorderSegmentEvent) => void;
}

export function useLiveRecorderSession(
  options: UseLiveRecorderSessionOptions = {},
): UseLiveRecorderSessionResult {
  const native = isTauriRuntime();
  const [busy, setBusy] = useState(false);
  const [statusRaw, setStatusRaw] = useState<Record<string, unknown> | null>(null);
  const [capabilities, setCapabilities] = useState<NativeCapabilities | null>(null);
  const [previewFrame, setPreviewFrame] = useState<RecorderPreviewFrame | null>(null);
  const [segments, setSegments] = useState<readonly RecorderSegmentEvent[]>([]);
  const [timeline, setTimeline] = useState<readonly TimelineEntry[]>([]);
  const [warnings, setWarnings] = useState<readonly string[]>([]);
  const [errors, setErrors] = useState<readonly string[]>([]);
  const unlistenersRef = useRef<Array<() => void>>([]);
  // Latest relay callback without re-binding native listeners per render.
  const optionsRef = useRef(options);
  optionsRef.current = options;

  // ── Event bindings (Tauri only) ────────────────────────────────────────────
  useEffect(() => {
    if (!native) return;

    let cancelled = false;
    const bind = async (): Promise<void> => {
      const { listen } = await import('@tauri-apps/api/event');
      if (cancelled) return;

      const unlisten: Array<() => void> = [];
      unlisten.push(await listen<Record<string, unknown>>('recorder://status', (ev) => {
        setStatusRaw(ev.payload);
      }));
      unlisten.push(await listen<RecorderPreviewFrame>('recorder://preview', (ev) => {
        // Only the newest frame matters for display; sampler gates what Gemini sees.
        setPreviewFrame(ev.payload);
      }));
      unlisten.push(await listen<RecorderSegmentEvent>('recorder://segment', (ev) => {
        setSegments((prev) => [...prev.slice(-49), ev.payload]);
        try {
          optionsRef.current.onSegmentEvent?.(ev.payload);
        } catch { /* relay is best-effort — never break the event pipeline */ }
      }));
      unlisten.push(await listen<TimelineEntry>('recorder://timeline', (ev) => {
        setTimeline((prev) => {
          const next = [...prev, ev.payload];
          return next.length > MAX_LOG_LINES ? next.slice(next.length - MAX_LOG_LINES) : next;
        });
      }));
      unlisten.push(await listen<{ message?: string }>('recorder://warning', (ev) => {
        setWarnings((prev) => pushBounded([...prev], ev.payload?.message ?? JSON.stringify(ev.payload)));
      }));
      unlisten.push(await listen<{ message?: string }>('recorder://error', (ev) => {
        setErrors((prev) => pushBounded([...prev], ev.payload?.message ?? JSON.stringify(ev.payload)));
      }));

      unlistenersRef.current = unlisten;
    };

    void bind();
    return () => {
      cancelled = true;
      for (const off of unlistenersRef.current) off();
      unlistenersRef.current = [];
    };
  }, [native]);

  const invokeCommand = useCallback(
    async <T,>(command: RecorderCommand, args?: Record<string, unknown>): Promise<T | null> => {
      if (!native) return null;
      setBusy(true);
      try {
        const mod = await import('@tauri-apps/api/core');
        return await mod.invoke<T>(command, args);
      } catch (e) {
        setErrors((prev) => pushBounded([...prev], `${command}: ${e instanceof Error ? e.message : String(e)}`));
        return null;
      } finally {
        setBusy(false);
      }
    },
    [native],
  );

  const prepare = useCallback(
    (request: RecorderPrepareRequest) => invokeCommand<Record<string, unknown>>('recorder_prepare', { request }),
    [invokeCommand],
  );

  const start = useCallback(
    (request: RecorderStartRequest) => invokeCommand<Record<string, unknown>>('recorder_start', { request }),
    [invokeCommand],
  );

  const pause = useCallback(() => invokeCommand<Record<string, unknown>>('recorder_pause'), [invokeCommand]);
  const resume = useCallback(() => invokeCommand<Record<string, unknown>>('recorder_resume'), [invokeCommand]);
  const stop = useCallback(() => invokeCommand<Record<string, unknown>>('recorder_stop'), [invokeCommand]);

  const createMarker = useCallback(
    (request: MarkerRequest) => invokeCommand<string>('recorder_create_marker', { request }),
    [invokeCommand],
  );

  const refreshStatus = useCallback(async () => {
    const raw = await invokeCommand<Record<string, unknown>>('recorder_get_status');
    if (raw) setStatusRaw(raw);
  }, [invokeCommand]);

  const refreshCapabilities = useCallback(async () => {
    const raw = await invokeCommand<Record<string, unknown>>('recorder_get_capabilities');
    if (raw && typeof raw === 'object') {
      setCapabilities(raw as unknown as NativeCapabilities);
    }
  }, [invokeCommand]);

  const dismissErrors = useCallback(() => setErrors([]), []);

  // Poll status at 1 Hz while native — mirrors the sidecar heartbeat.
  useEffect(() => {
    if (!native) return;
    void refreshStatus();
    const interval = setInterval(() => void refreshStatus(), 1000);
    return () => clearInterval(interval);
  }, [native, refreshStatus]);

  const derivedStatus: RecorderStatus | null = statusRaw !== null && isRecorderStatus(statusRaw)
    ? (statusRaw as unknown as RecorderStatus)
    : null;

  return {
    native,
    busy,
    status: derivedStatus,
    statusRaw,
    capabilities,
    previewFrame,
    segments,
    timeline,
    warnings,
    errors,
    prepare,
    start,
    pause,
    resume,
    stop,
    createMarker,
    refreshStatus,
    refreshCapabilities,
    dismissErrors,
  };
}
