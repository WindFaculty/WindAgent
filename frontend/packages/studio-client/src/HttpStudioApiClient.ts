/**
 * HttpStudioApiClient — real HTTP client for the frozen /api/v3/studio surface
 * (studio.contract/v0.1, Plan C2).
 *
 * Rules enforced here:
 * - Mutations REQUIRE an explicit idempotency key; the caller owns the key and
 *   must keep it stable across transport retries (this client never retries a
 *   mutation, so a failed POST can be safely replayed by the caller with the
 *   same key).
 * - GETs may retry once on network failure only (safe, idempotent).
 * - Server error payloads map to typed StudioApiError; retryable/conflict/
 *   capability codes stay machine-readable. No synthesized success.
 */

import type {
  StudioArtifactEnvelope,
  StudioEpisode,
  StudioErrorPayload,
  StudioRunResource,
  StudioSeries,
} from '@windagent/studio-contracts';

export type StudioErrorCode = StudioErrorPayload['code'];

export class StudioApiError extends Error {
  readonly code: StudioErrorCode;
  readonly status: number;
  readonly retryable: boolean;
  readonly details?: Record<string, unknown>;
  readonly correlationId?: string;

  constructor(payload: StudioErrorPayload) {
    super(payload.detail || payload.title);
    this.name = 'StudioApiError';
    this.code = payload.code;
    this.status = payload.status;
    this.retryable = payload.retryable === true;
    this.details = payload.details;
    this.correlationId = payload.correlation_id;
  }
}

export class StudioNetworkError extends Error {
  readonly retryable = true;
  constructor(message: string) {
    super(message);
    this.name = 'StudioNetworkError';
  }
}

/** A response reached the Studio API but could not be mapped to its error contract. */
export class StudioHttpError extends Error {
  readonly retryable: boolean;

  constructor(
    readonly status: number,
    readonly statusText: string,
  ) {
    super(`Studio API returned HTTP ${status}${statusText ? `: ${statusText}` : ''}`);
    this.name = 'StudioHttpError';
    this.retryable = status >= 500;
  }
}

export class StudioTimeoutError extends StudioNetworkError {
  constructor() {
    super('Studio request timed out');
    this.name = 'StudioTimeoutError';
  }
}

export interface StudioClientOptions {
  baseUrl: string;
  actor?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export interface SeriesCreated {
  series_id: string;
  title: string;
  series_url: string;
}

export interface EpisodeCreated {
  episode_id: string;
  title: string;
  episode_url: string;
}

export interface RunStarted {
  run_id: string;
  episode_id: string;
  resuming: boolean;
  run_url: string;
}

export interface IdeaSelected {
  episode_id: string;
  candidate_id: string;
  revision_id: string;
  content_hash: string;
  optimistic_version: number;
  replayed: boolean;
}

export interface ApprovalRecorded {
  episode_id: string;
  checkpoint: string;
  next_state: string;
  awaiting_approval: boolean;
}

export interface RevisionDerived {
  revision_id: string;
  parent_revision_id: string;
  episode_id: string;
  revision_url: string;
}

export interface ScreenplayLocked {
  episode_id: string;
  revision_id: string;
  lock_receipt_artifact_id: string;
  state: string;
}

export interface RunEventEnvelope {
  sequence: number;
  event_type: string;
  [k: string]: unknown;
}

export interface RunEventsPage {
  events: RunEventEnvelope[];
  next_after: number;
}

export interface RuntimeCapability {
  name: string;
  status: 'AVAILABLE' | 'DEGRADED' | 'UNAVAILABLE';
  reason: string;
  [k: string]: unknown;
}

export interface CapabilityProfile {
  capabilities: RuntimeCapability[];
  fail_closed_flags: string[];
  certification_mode: boolean;
}

interface JsonBody {
  [k: string]: unknown;
}

export class HttpStudioApiClient {
  private readonly baseUrl: string;
  private readonly actor?: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: StudioClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.actor = options.actor;
    this.timeoutMs = options.timeoutMs ?? 15_000;
    const defaultFetch =
      typeof window !== 'undefined'
        ? window.fetch.bind(window)
        : typeof globalThis !== 'undefined'
        ? globalThis.fetch.bind(globalThis)
        : fetch;
    this.fetchImpl = options.fetchImpl ?? defaultFetch;
  }

  // -- reads -------------------------------------------------------------

  listSeries(): Promise<{ items: StudioSeries[] }> {
    return this.getJson('/api/v3/studio/series');
  }

  getSeries(seriesId: string): Promise<StudioSeries> {
    return this.getJson(`/api/v3/studio/series/${encodeURIComponent(seriesId)}`);
  }

  listEpisodes(seriesId: string): Promise<{ items: StudioEpisode[] }> {
    return this.getJson(
      `/api/v3/studio/series/${encodeURIComponent(seriesId)}/episodes`
    );
  }

  getEpisode(episodeId: string): Promise<StudioEpisode> {
    return this.getJson(`/api/v3/studio/episodes/${encodeURIComponent(episodeId)}`);
  }

  getRun(runId: string): Promise<StudioRunResource> {
    return this.getJson(`/api/v3/studio/runs/${encodeURIComponent(runId)}`);
  }

  getRunEvents(runId: string, after: number): Promise<RunEventsPage> {
    return this.getJson(
      `/api/v3/studio/runs/${encodeURIComponent(runId)}/events?after=${after}`
    );
  }

  listArtifacts(episodeId: string): Promise<{ items: StudioArtifactEnvelope[] }> {
    return this.getJson(
      `/api/v3/studio/episodes/${encodeURIComponent(episodeId)}/artifacts`
    );
  }

  getArtifact(artifactId: string): Promise<StudioArtifactEnvelope> {
    return this.getJson(`/api/v3/studio/artifacts/${encodeURIComponent(artifactId)}`);
  }

  getCapabilities(): Promise<CapabilityProfile> {
    return this.getJson('/api/v3/studio/capabilities');
  }

  getReadiness(): Promise<{ ready: boolean; [k: string]: unknown }> {
    return this.getJson('/api/v3/studio/readiness');
  }

  // -- mutations (idempotency key required, never auto-retried) ----------

  createSeries(key: string, body: { title: string; description?: string }): Promise<SeriesCreated> {
    return this.postJson('/api/v3/studio/series', key, body);
  }

  createEpisode(key: string, seriesId: string, body: { title: string; brief?: string }): Promise<EpisodeCreated> {
    return this.postJson(
      `/api/v3/studio/series/${encodeURIComponent(seriesId)}/episodes`,
      key,
      body
    );
  }

  startRun(key: string, episodeId: string): Promise<RunStarted> {
    return this.postJson(
      `/api/v3/studio/episodes/${encodeURIComponent(episodeId)}/runs`,
      key,
      {}
    );
  }

  selectIdea(key: string, episodeId: string, body: {
    episode_id: string;
    revision_id: string;
    candidate_id: string;
    expected_content_hash: string;
    expected_optimistic_version: number;
  }): Promise<IdeaSelected> {
    return this.postJson(
      `/api/v3/studio/episodes/${encodeURIComponent(episodeId)}/idea-selection`,
      key,
      body
    );
  }

  recordApproval(key: string, episodeId: string, body: {
    episode_id: string;
    revision_id: string;
    checkpoint: string;
    artifact_hash: string;
    decision: 'APPROVED' | 'REJECTED' | 'REQUEST_REVISION';
    reason?: string;
    expected_optimistic_version: number;
  }): Promise<ApprovalRecorded> {
    return this.postJson(
      `/api/v3/studio/episodes/${encodeURIComponent(episodeId)}/approvals`,
      key,
      body
    );
  }

  deriveRevision(key: string, episodeId: string, body: {
    episode_id: string;
    series_id: string;
    parent_revision_id: string;
    new_content_hash: string;
    invalidation_intent?: string;
    summary?: string;
    expected_optimistic_version: number;
  }): Promise<RevisionDerived> {
    return this.postJson(
      `/api/v3/studio/episodes/${encodeURIComponent(episodeId)}/revisions`,
      key,
      body
    );
  }

  lockScreenplay(key: string, episodeId: string, body: {
    episode_id: string;
    revision_id: string;
    expected_content_hash: string;
    expected_optimistic_version: number;
  }): Promise<ScreenplayLocked> {
    return this.postJson(
      `/api/v3/studio/episodes/${encodeURIComponent(episodeId)}/screenplay-lock`,
      key,
      body
    );
  }

  // -- internals ---------------------------------------------------------

  private async request(path: string, init: RequestInit, allowRetry: boolean): Promise<Response> {
    const doFetch = async (): Promise<Response> => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);
      try {
        return await this.fetchImpl(this.baseUrl + path, {
          ...init,
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timer);
      }
    };

    try {
      return await doFetch();
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new StudioTimeoutError();
      }
      if (allowRetry) {
        try {
          return await doFetch();
        } catch (retryErr) {
          if (retryErr instanceof StudioTimeoutError) throw retryErr;
          throw new StudioNetworkError(
            `Studio request failed: ${String(retryErr)}`
          );
        }
      }
      throw new StudioNetworkError(`Studio request failed: ${String(err)}`);
    }
  }

  private async getJson<T>(path: string): Promise<T> {
    const res = await this.request(path, { method: 'GET' }, true);
    return this.parse<T>(res);
  }

  private async postJson<T>(path: string, key: string, body: JsonBody): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Idempotency-Key': key,
    };
    if (this.actor) headers['X-WindAgent-Actor'] = this.actor;
    const res = await this.request(
      path,
      { method: 'POST', headers, body: JSON.stringify(body) },
      false
    );
    return this.parse<T>(res);
  }

  private async parse<T>(res: Response): Promise<T> {
    if (res.ok) {
      return (await res.json()) as T;
    }
    let payload: StudioErrorPayload;
    try {
      payload = (await res.json()) as StudioErrorPayload;
    } catch {
      throw new StudioHttpError(res.status, res.statusText);
    }
    if (payload && typeof payload.code === 'string') {
      throw new StudioApiError(payload);
    }
    throw new StudioHttpError(res.status, res.statusText);
  }
}

export function isStudioApiError(err: unknown): err is StudioApiError {
  return err instanceof StudioApiError;
}

export function isRetryableError(err: unknown): boolean {
  if (err instanceof StudioNetworkError) return true;
  return err instanceof StudioApiError && err.retryable;
}
