/**
 * StudioStore — client-side state/query layer for /api/v3/studio (Plan C2).
 *
 * Authority rules implemented here:
 * - Server state is the authority. This store NEVER advances a run stage or
 *   marks an artifact/revision/lock as durable on its own; mutations go
 *   through the API and state refreshes from server responses.
 * - Optimistic state is limited to a PENDING marker on the in-flight command;
 *   a refresh that disagrees with pending state wins.
 * - Idempotency keys are owned by the caller and kept stable across retries;
 *   the store never mints a new key for a replayed command.
 * - Event cursor is advanced only from server `next_after`; restart hydration
 *   restores the cursor so polling resumes without gaps or duplicates.
 * - Unknown artifact schema/type surfaces an explicit unsupported-schema
 *   state, never a blank or synthesized view.
 */

import type {
  StudioArtifactEnvelope,
  StudioEpisode,
  StudioRunResource,
  StudioSeries,
} from '@windagent/studio-contracts';
import {
  HttpStudioApiClient,
  StudioApiError,
  StudioNetworkError,
  type CapabilityProfile,
  type RunEventsPage,
  type RuntimeCapability,
  type SeriesCreated,
  type EpisodeCreated,
  type RunStarted,
  type IdeaSelected,
  type ApprovalRecorded,
  type RevisionDerived,
  type ScreenplayLocked,
} from '@windagent/studio-client';

export type StoreErrorKind =
  | 'capability_unavailable'
  | 'conflict'
  | 'network'
  | 'validation'
  | 'not_found'
  | 'unsupported_schema'
  | 'unknown';

export interface StoreError {
  kind: StoreErrorKind;
  message: string;
  code?: string;
  details?: Record<string, unknown>;
}

export interface StudioSnapshot {
  eventCursors: Record<string, number>;
}

const TERMINAL_RUN_STATUSES = new Set(['COMPLETED', 'FAILED', 'CANCELLED']);

export class StudioStore {
  private readonly client: HttpStudioApiClient;

  private series = new Map<string, StudioSeries>();
  private seriesList: string[] = [];
  private episodes = new Map<string, StudioEpisode>();
  private episodesBySeries = new Map<string, string[]>();
  private runs = new Map<string, StudioRunResource>();
  private artifactsByEpisode = new Map<string, StudioArtifactEnvelope[]>();
  private eventCursors = new Map<string, number>();
  private pendingCommands = new Set<string>();
  private capabilities: RuntimeCapability[] = [];
  private lastError: StoreError | null = null;
  private conflict: { episode_id: string; code: string; details?: Record<string, unknown> } | null = null;
  private pollTimers = new Map<string, ReturnType<typeof setInterval>>();

  constructor(client: HttpStudioApiClient) {
    this.client = client;
  }

  // -- reads -------------------------------------------------------------

  getSeriesList(): StudioSeries[] {
    return this.seriesList
      .map((id) => this.series.get(id))
      .filter((s): s is StudioSeries => s !== undefined);
  }

  getSeries(id: string): StudioSeries | undefined {
    return this.series.get(id);
  }

  getEpisodes(seriesId: string): StudioEpisode[] {
    return (this.episodesBySeries.get(seriesId) ?? [])
      .map((id) => this.episodes.get(id))
      .filter((e): e is StudioEpisode => e !== undefined);
  }

  getEpisode(id: string): StudioEpisode | undefined {
    return this.episodes.get(id);
  }

  getRun(runId: string): StudioRunResource | undefined {
    return this.runs.get(runId);
  }

  getArtifacts(episodeId: string): StudioArtifactEnvelope[] {
    return this.artifactsByEpisode.get(episodeId) ?? [];
  }

  getEventCursor(runId: string): number {
    return this.eventCursors.get(runId) ?? 0;
  }

  isPending(key: string): boolean {
    return this.pendingCommands.has(key);
  }

  getLastError(): StoreError | null {
    return this.lastError;
  }

  getConflict(): { episode_id: string; code: string; details?: Record<string, unknown> } | null {
    return this.conflict;
  }

  getCapabilityStatus(name: string): string | undefined {
    return this.capabilities.find((c) => c.name === name)?.status;
  }

  isUnsupportedSchema(artifact: StudioArtifactEnvelope): boolean {
    return !artifact.schema_version.startsWith('studio.artifact/v1alpha1');
  }

  // -- loaders -----------------------------------------------------------

  async loadSeriesList(): Promise<StudioSeries[]> {
    const data = await this.withErrors(async () => this.client.listSeries());
    if (!data) return this.getSeriesList();
    this.seriesList = data.items.map((s) => s.id);
    for (const s of data.items) this.series.set(s.id, s);
    return this.getSeriesList();
  }

  async loadSeries(id: string): Promise<StudioSeries | undefined> {
    const s = await this.withErrors(async () => this.client.getSeries(id));
    if (s) this.series.set(s.id, s);
    return s ?? undefined;
  }

  async loadEpisodes(seriesId: string): Promise<StudioEpisode[]> {
    const data = await this.withErrors(async () => this.client.listEpisodes(seriesId));
    if (!data) return this.getEpisodes(seriesId);
    this.episodesBySeries.set(
      seriesId,
      data.items.map((e) => e.id)
    );
    for (const e of data.items) this.episodes.set(e.id, e);
    return this.getEpisodes(seriesId);
  }

  async loadEpisode(id: string): Promise<StudioEpisode | undefined> {
    const e = await this.withErrors(async () => this.client.getEpisode(id));
    if (e) this.episodes.set(e.id, e);
    return e ?? undefined;
  }

  async loadRun(runId: string): Promise<StudioRunResource | undefined> {
    const r = await this.withErrors(async () => this.client.getRun(runId));
    if (r) this.runs.set(r.run_id, r);
    return r ?? undefined;
  }

  async loadArtifacts(episodeId: string): Promise<StudioArtifactEnvelope[]> {
    const data = await this.withErrors(async () => this.client.listArtifacts(episodeId));
    if (!data) return this.getArtifacts(episodeId);
    this.artifactsByEpisode.set(episodeId, data.items);
    return data.items;
  }

  async loadCapabilities(): Promise<CapabilityProfile | null> {
    const profile = await this.withErrors(async () => this.client.getCapabilities());
    if (profile) this.capabilities = profile.capabilities;
    return profile;
  }

  // -- mutations (idempotency key from caller, stable across retries) ----

  async createSeries(key: string, title: string, description?: string): Promise<SeriesCreated | null> {
    return this.runCommand(key, () => this.client.createSeries(key, { title, description }), () => {
      void this.loadSeriesList();
    });
  }

  async createEpisode(key: string, seriesId: string, title: string, brief?: string): Promise<EpisodeCreated | null> {
    return this.runCommand(key, () => this.client.createEpisode(key, seriesId, { title, brief }), () => {
      void this.loadEpisodes(seriesId);
      void this.loadSeries(seriesId);
    });
  }

  async startRun(key: string, episodeId: string): Promise<RunStarted | null> {
    return this.runCommand(key, () => this.client.startRun(key, episodeId), () => {
      void this.loadEpisode(episodeId);
    });
  }

  async selectIdea(key: string, episodeId: string, body: Parameters<HttpStudioApiClient['selectIdea']>[2]): Promise<IdeaSelected | null> {
    return this.runCommand(key, () => this.client.selectIdea(key, episodeId, body), () => {
      void this.loadEpisode(episodeId);
    });
  }

  async recordApproval(key: string, episodeId: string, body: Parameters<HttpStudioApiClient['recordApproval']>[2]): Promise<ApprovalRecorded | null> {
    return this.runCommand(key, () => this.client.recordApproval(key, episodeId, body), () => {
      void this.loadEpisode(episodeId);
      void this.loadArtifacts(episodeId);
    });
  }

  async deriveRevision(key: string, episodeId: string, body: Parameters<HttpStudioApiClient['deriveRevision']>[2]): Promise<RevisionDerived | null> {
    return this.runCommand(key, () => this.client.deriveRevision(key, episodeId, body), () => {
      void this.loadEpisode(episodeId);
      void this.loadArtifacts(episodeId);
    });
  }

  async lockScreenplay(key: string, episodeId: string, body: Parameters<HttpStudioApiClient['lockScreenplay']>[2]): Promise<ScreenplayLocked | null> {
    return this.runCommand(key, () => this.client.lockScreenplay(key, episodeId, body), () => {
      void this.loadEpisode(episodeId);
      void this.loadArtifacts(episodeId);
    });
  }

  // -- run polling -------------------------------------------------------

  /**
   * Polls run status and advances the event cursor from server `next_after`.
   * Stops on terminal status. Returns a stop function.
   */
  pollRun(
    runId: string,
    opts: { intervalMs?: number; onEvent?: (events: RunEventsPage['events']) => void; onStatus?: (run: StudioRunResource) => void } = {}
  ): () => void {
    this.stopPolling(runId);
    const intervalMs = opts.intervalMs ?? 2_000;
    const tick = async () => {
      try {
        const run = await this.client.getRun(runId);
        this.runs.set(run.run_id, run);
        opts.onStatus?.(run);
        const after = this.eventCursors.get(runId) ?? 0;
        const page = await this.client.getRunEvents(runId, after);
        // server-declared cursor wins even on empty pages (events may be
        // skipped/compact); events are delivered once per sequence
        if (typeof page.next_after === 'number' && page.next_after > after) {
          this.eventCursors.set(runId, page.next_after);
        }
        if (page.events.length > 0) {
          opts.onEvent?.(page.events);
        }
        if (TERMINAL_RUN_STATUSES.has(run.status)) {
          this.stopPolling(runId);
        }
      } catch (err) {
        this.recordError(err);
      }
    };
    void tick();
    const timer = setInterval(() => void tick(), intervalMs);
    this.pollTimers.set(runId, timer);
    return () => this.stopPolling(runId);
  }

  stopPolling(runId: string): void {
    const timer = this.pollTimers.get(runId);
    if (timer) {
      clearInterval(timer);
      this.pollTimers.delete(runId);
    }
  }

  stopAllPolling(): void {
    for (const runId of [...this.pollTimers.keys()]) this.stopPolling(runId);
  }

  // -- restart hydration -------------------------------------------------

  serialize(): StudioSnapshot {
    return {
      eventCursors: Object.fromEntries(this.eventCursors),
    };
  }

  hydrate(snapshot: StudioSnapshot): void {
    for (const [runId, cursor] of Object.entries(snapshot.eventCursors)) {
      this.eventCursors.set(runId, cursor);
    }
  }

  // -- internals ---------------------------------------------------------

  private async runCommand<T>(
    key: string,
    execute: () => Promise<T>,
    invalidate: () => void
  ): Promise<T | null> {
    this.pendingCommands.add(key);
    try {
      const result = await this.withErrors(execute);
      if (result !== null) {
        // success: clear stale conflict and refresh affected views
        this.conflict = null;
        invalidate();
      }
      return result;
    } finally {
      this.pendingCommands.delete(key);
    }
  }

  private async withErrors<T>(fn: () => Promise<T>): Promise<T | null> {
    try {
      return await fn();
    } catch (err) {
      this.recordError(err);
      return null;
    }
  }

  private recordError(err: unknown): void {
    if (err instanceof StudioApiError) {
      if (err.code === 'CAPABILITY_UNAVAILABLE' || err.code === 'PROVIDER_UNAVAILABLE') {
        this.lastError = { kind: 'capability_unavailable', message: err.message, code: err.code };
      } else if (err.code === 'STALE_REVISION' || err.code === 'ARTIFACT_HASH_MISMATCH' || err.code === 'LOCKED_REVISION') {
        this.lastError = { kind: 'conflict', message: err.message, code: err.code, details: err.details };
        const episodeId = String(err.details?.episode_id ?? err.details?.revision_id ?? '');
        if (episodeId) {
          this.conflict = { episode_id: episodeId, code: err.code, details: err.details };
          void this.loadEpisode(episodeId);
        }
      } else if (err.code === 'NOT_FOUND') {
        this.lastError = { kind: 'not_found', message: err.message, code: err.code };
      } else if (err.code === 'VALIDATION_ERROR' || err.code === 'INVALID_TRANSITION' || err.code === 'APPROVAL_REQUIRED' || err.code === 'IDEMPOTENCY_MISMATCH') {
        this.lastError = { kind: 'validation', message: err.message, code: err.code, details: err.details };
      } else {
        this.lastError = { kind: 'unknown', message: err.message, code: err.code };
      }
      return;
    }
    if (err instanceof StudioNetworkError) {
      this.lastError = { kind: 'network', message: err.message };
      return;
    }
    this.lastError = { kind: 'unknown', message: String(err) };
  }
}
