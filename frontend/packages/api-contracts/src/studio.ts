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

export interface StudioSeriesResource {
  id: string;
  title: string;
  description: string;
  episode_ids: string[];
  episode_count: number;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
  series_url: string;
}

export interface StudioSeriesListResponse {
  items: StudioSeriesResource[];
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

export interface StudioEpisodeResource {
  id: string;
  series_id: string;
  title: string;
  episode_number: number;
  state: string;
  version: number;
  optimistic_version: number;
  current_revision_id: string | null;
  active_run_id: string | null;
  episode_url: string;
  run_url: string | null;
  awaiting_checkpoint?: string | null;
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, unknown>;
  current_revision?: Record<string, unknown> | null;
  approvals?: Array<Record<string, unknown>> | null;
  artifact_summary?: {
    count: number;
    types: string[];
  } | null;
}

export interface StudioEpisodeListResponse {
  items: StudioEpisodeResource[];
}

export interface StudioEpisodeCreateResponse {
  episode_id: string;
  series_id: string;
  state: string;
  episode_url: string;
}

export interface StudioUpdateEpisodeRequest {
  title?: string;
  metadata_patch?: Record<string, unknown>;
  expected_optimistic_version?: number;
}

export interface StudioUpdateEpisodeResponse {
  episode_id: string;
  state: string;
  optimistic_version: number;
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

// ── P0.7 Decision & Lifecycle Mutations ────────────────────────────────────

export interface StudioSelectIdeaRequest {
  episode_id: string;
  revision_id: string;
  candidate_id: string;
  expected_content_hash: string;
  expected_optimistic_version?: number;
}

export interface StudioSelectIdeaResponse {
  episode_id: string;
  candidate_id: string;
  revision_id: string;
  content_hash: string;
  optimistic_version: number;
  replayed: boolean;
}

export interface StudioRecordApprovalRequest {
  episode_id: string;
  revision_id: string;
  checkpoint: string;
  artifact_hash: string;
  decision: 'APPROVED' | 'REVISE' | 'REJECTED' | string;
  reason?: string;
  expected_optimistic_version?: number;
}

export interface StudioRecordApprovalResponse {
  episode_id: string;
  checkpoint: string;
  next_state?: string | null;
  awaiting_approval: boolean;
}

export interface StudioDeriveRevisionRequest {
  episode_id: string;
  series_id: string;
  parent_revision_id: string;
  new_content_hash: string;
  summary: string;
  invalidation_intent?: string | null;
  expected_optimistic_version?: number;
}

export interface StudioDeriveRevisionResponse {
  revision_id: string;
  parent_revision_id: string;
  episode_id: string;
  revision_url: string;
}

export interface StudioLockScreenplayRequest {
  episode_id: string;
  revision_id: string;
  expected_content_hash: string;
  expected_optimistic_version?: number;
}

export interface StudioLockScreenplayResponse {
  episode_id: string;
  revision_id: string;
  lock_receipt_artifact_id?: string | null;
  state: string;
}

