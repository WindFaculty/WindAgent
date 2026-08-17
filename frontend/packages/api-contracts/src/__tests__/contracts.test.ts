/**
 * API Contracts — Canonical V3 contract freeze validation (Phase 9.0 / 12.0).
 * Guards the shared vocabulary: IDs, optimistic locking fields, and
 * revision-pinned decision payloads.
 */
import { describe, it, expect } from 'vitest';
import type {
  AssetProvenance,
  AssetResource,
  ReviewDecisionResource,
  RoutingRuleResource,
  SceneResource,
  JobSubmissionReceipt,
} from '../index';

describe('Phase 9.0 — shared contract freeze', () => {
  it('AssetResource carries durable provenance for downstream reuse', () => {
    const provenance: AssetProvenance = {
      source: 'generation',
      generator: 'storyboard_concept_gen',
      model: 'stable-diffusion-3',
      job_id: 'job_abc',
      content_hash: 'sha256:abc',
      parent_revision_id: 'rev_1',
      created_at: '2026-08-01T00:00:00Z',
    };
    expect(provenance.content_hash).toBe('sha256:abc');
    expect(provenance.job_id).toBe('job_abc');

    const asset: AssetResource = {
      id: 'asset_1',
      name: 'Concept Hero',
      type: 'IMAGE',
      status: 'APPROVED',
      provenance,
      version: 3,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
    };
    expect(asset.provenance.parent_revision_id).toBe('rev_1');
  });

  it('SceneResource pins source_screenplay_revision_id', () => {
    const scene: SceneResource = {
      id: 'scene_1',
      storyboard_id: 'sb_1',
      source_screenplay_revision_id: 'rev_9',
      index: 0,
      description: 'Opening wide shot',
      version: 1,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
    };
    expect(scene.source_screenplay_revision_id).toBe('rev_9');
  });

  it('ReviewDecisionResource is pinned to revision + expected_version', () => {
    const decision: ReviewDecisionResource = {
      decision: 'APPROVED',
      revision_id: 'rev_7',
      expected_version: 12,
      reason: 'Meets audience band',
    };
    expect(decision.decision).toBe('APPROVED');
    expect(decision.revision_id).toBe('rev_7');
    expect(decision.expected_version).toBe(12);
  });

  it('RoutingRuleResource keeps version for optimistic locking', () => {
    const rule: RoutingRuleResource = {
      id: 'rule_1',
      name: 'Local-first planning',
      version: 2,
      enabled: true,
      priority: 10,
      canonical_model_id: 'gemini-2.5-pro',
      description: 'Route planning to local provider',
      task_labels: ['planning'],
      agent_types: ['Coordinator'],
      workflow_types: [],
      required_capabilities: ['reasoning'],
      min_context_tokens: 8192,
      requires_tools: true,
      requires_vision: false,
      cost_classes: ['standard'],
      requires_local: true,
      requires_private: false,
      primary_usage: 42,
      fallback_usage: 3,
      success_rate: 0.97,
      avg_latency_ms: 1240,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
    };
    expect(rule.version).toBe(2);
    expect(rule.requires_local).toBe(true);
  });

  it('JobSubmissionReceipt exposes canonical QUEUED receipt', () => {
    const receipt: JobSubmissionReceipt = {
      job_id: 'job_1',
      state: 'QUEUED',
      submitted_at: '2026-08-01T00:00:00Z',
      correlation_id: 'corr_1',
    };
    expect(receipt.state).toBe('QUEUED');
    expect(receipt.correlation_id).toBe('corr_1');
  });
});
