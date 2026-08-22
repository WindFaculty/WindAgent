/**
 * Canonical Studio V3 Capabilities and Runtime Contracts.
 */

export interface CapabilitySummary {
  name: string;
  status: 'AVAILABLE' | 'DEGRADED' | 'UNAVAILABLE' | string;
  detail?: string | null;
}

export interface RuntimeCapabilityProfile {
  capabilities: CapabilitySummary[];
  fail_closed_flags: string[];
  certification_mode: boolean;
}

export interface ReadinessResponse {
  status: 'READY' | 'DEGRADED' | 'UNAVAILABLE' | string;
  capabilities: Record<string, string>;
  fail_closed_flags: string[];
  certification_mode: boolean;
}

// ── P0.7 — canonical Series / Episodes / Runs / Preflight ─────────────────

export interface StudioSeriesListResponse {
  items: Array<Record<string, unknown>>;
  next_cursor?: string | null;
}

export interface StudioSeriesCreateResponse {
  series_id: string;
  title: string;
  series_url: string;
}

export interface StudioSeriesUpdateResponse {
  series_id: string;
  title: string;
  series_url: string;
}

export interface StudioEpisodeListResponse {
  items: Array<Record<string, unknown>>;
}

export interface StudioEpisodeCreateResponse {
  episode_id: string;
  series_id: string;
  state: string;
  episode_url: string;
}

/** P0.4.1 — truthful per-check Story Start preflight report. */
export interface StudioPreflightCheck {
  name: string;
  status: 'PASS' | 'FAIL' | 'WARN';
  detail: string;
}

export interface StudioPreflightReport {
  episode_id: string;
  ready: boolean;
  checks: StudioPreflightCheck[];
}
