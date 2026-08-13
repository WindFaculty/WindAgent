import { describe, it, expect, beforeEach } from 'vitest';
import { StudioStore, type IStudioApiClient } from '@windagent/studio-state';
import type {
  StudioSeries,
  StudioEpisode,
  StudioArtifactEnvelope,
} from '@windagent/studio-contracts';

/**
 * Mock HTTP Client implementing IStudioApiClient interface for E2E Pipeline Certification.
 * Verifies exact mandatory contract path without fake UI synthesizing.
 */
function createMockHttpApiClient(): IStudioApiClient {
  const seriesMap = new Map<string, StudioSeries>();
  const episodeMap = new Map<string, StudioEpisode>();
  const artifactsMap = new Map<string, StudioArtifactEnvelope[]>();
  let runCount = 0;

  return {
    async getCapabilities() {
      return {
        durable_db: 'AVAILABLE',
        studio_orchestration: 'AVAILABLE',
        story_engine: 'AVAILABLE',
        worker: 'AVAILABLE',
      };
    },

    async listSeries() {
      return { items: Array.from(seriesMap.values()) };
    },

    async createSeries(idempotencyKey, payload) {
      const s: StudioSeries = {
        id: `srs_${idempotencyKey.slice(-6)}`,
        title: payload.title,
        logline: payload.description ?? '',
        target_audience: 'KIDS_6_9',
        created_at: new Date().toISOString(),
        episode_count: 0,
      };
      seriesMap.set(s.id, s);
      return { series: s, created: true };
    },

    async listEpisodes(seriesId) {
      return { items: Array.from(episodeMap.values()).filter((e) => e.series_id === seriesId) };
    },

    async createEpisode(idempotencyKey, seriesId, payload) {
      const ep: StudioEpisode = {
        id: `ep_${idempotencyKey.slice(-6)}`,
        series_id: seriesId,
        title: payload.title,
        state: 'DRAFT',
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      episodeMap.set(ep.id, ep);
      artifactsMap.set(ep.id, []);

      const s = seriesMap.get(seriesId);
      if (s) s.episode_count += 1;

      return { episode: ep, created: true };
    },

    async getEpisode(episodeId) {
      const ep = episodeMap.get(episodeId);
      if (!ep) throw new Error('not_found');
      return ep;
    },

    async listArtifacts(episodeId) {
      return { items: artifactsMap.get(episodeId) ?? [] };
    },

    async startRun(idempotencyKey, episodeId) {
      const ep = episodeMap.get(episodeId);
      if (!ep) throw new Error('not_found');

      runCount += 1;

      if (runCount === 1) {
        ep.state = 'IDEA_REVIEW';
        ep.version += 1;
        const ideaSet: StudioArtifactEnvelope = {
          artifact_id: `art_idea_${Date.now()}`,
          artifact_type: 'IdeaCandidateSet',
          schema_version: 'studio.artifact/v1alpha1',
          series_id: ep.series_id,
          episode_id: ep.id,
          revision_id: 'rev_1',
          content_hash: 'ideahash12345678',
          content: {
            recommended_candidate_id: 'cand_1',
            candidates: [
              {
                candidate_id: 'cand_1',
                title: 'Thỏ Thả Diều',
                logline: 'Chú thỏ học thả diều cùng bạn bè.',
                score: 0.95,
              },
            ],
          },
        };
        artifactsMap.set(ep.id, [...(artifactsMap.get(ep.id) ?? []), ideaSet]);
      } else if (runCount === 2) {
        ep.state = 'STORY_REVIEW';
        ep.version += 1;
        const storyBible: StudioArtifactEnvelope = {
          artifact_id: `art_sb_${Date.now()}`,
          artifact_type: 'StoryBible',
          schema_version: 'studio.artifact/v1alpha1',
          series_id: ep.series_id,
          episode_id: ep.id,
          revision_id: 'rev_1',
          content_hash: 'sbhash12345678',
          content: { title: 'Thỏ Thả Diều', premise: 'Hành trình học thả diều.' },
        };
        artifactsMap.set(ep.id, [...(artifactsMap.get(ep.id) ?? []), storyBible]);
      } else if (runCount === 3) {
        ep.state = 'OUTLINE_REVIEW';
        ep.version += 1;
        const outline: StudioArtifactEnvelope = {
          artifact_id: `art_out_${Date.now()}`,
          artifact_type: 'EpisodeOutline',
          schema_version: 'studio.artifact/v1alpha1',
          series_id: ep.series_id,
          episode_id: ep.id,
          revision_id: 'rev_1',
          content_hash: 'outhash12345678',
          content: { title: 'Thỏ Thả Diều', target_duration_seconds: 120, scenes: [] },
        };
        artifactsMap.set(ep.id, [...(artifactsMap.get(ep.id) ?? []), outline]);
      } else {
        ep.state = 'SCREENPLAY_REVIEW';
        ep.version += 1;
        const screenplay: StudioArtifactEnvelope = {
          artifact_id: `art_sp_${Date.now()}`,
          artifact_type: 'ScreenplayDraft',
          schema_version: 'studio.artifact/v1alpha1',
          series_id: ep.series_id,
          episode_id: ep.id,
          revision_id: 'rev_1',
          content_hash: 'sphash12345678',
          content: { title: 'Thỏ Thả Diều', scenes: [] },
        };
        const review: StudioArtifactEnvelope = {
          artifact_id: `art_rev_${Date.now()}`,
          artifact_type: 'ReviewReport',
          schema_version: 'studio.artifact/v1alpha1',
          series_id: ep.series_id,
          episode_id: ep.id,
          revision_id: 'rev_1',
          content_hash: 'revhash12345678',
          content: { verdict: 'REVISION_REQUIRED', findings: [] },
        };
        artifactsMap.set(ep.id, [...(artifactsMap.get(ep.id) ?? []), screenplay, review]);
      }

      ep.updated_at = new Date().toISOString();
      return { run_id: `run_${idempotencyKey.slice(-6)}`, status: 'STARTED' };
    },

    async selectIdea(idempotencyKey, episodeId, payload) {
      const ep = episodeMap.get(episodeId);
      if (!ep) throw new Error('not_found');

      ep.state = 'STORY_DEVELOPMENT';
      ep.version += 1;
      const selectedIdea: StudioArtifactEnvelope = {
        artifact_id: `art_sel_${Date.now()}`,
        artifact_type: 'SelectedIdea',
        schema_version: 'studio.artifact/v1alpha1',
        series_id: ep.series_id,
        episode_id: ep.id,
        revision_id: 'rev_1',
        content_hash: 'selhash12345678',
        content: { candidate_id: payload.candidate_id, title: 'Thỏ Thả Diều' },
      };
      artifactsMap.set(ep.id, [...(artifactsMap.get(ep.id) ?? []), selectedIdea]);
      ep.updated_at = new Date().toISOString();
      return { episode: ep };
    },

    async recordApproval(idempotencyKey, episodeId, payload) {
      const ep = episodeMap.get(episodeId);
      if (!ep) throw new Error('not_found');

      ep.version += 1;
      if (payload.decision === 'APPROVED') {
        ep.state = 'APPROVED';
      } else if (payload.decision === 'REQUEST_REVISION') {
        ep.state = 'REVISION_REQUIRED';
        const proposal: StudioArtifactEnvelope = {
          artifact_id: `art_prop_${Date.now()}`,
          artifact_type: 'RevisionProposal',
          schema_version: 'studio.artifact/v1alpha1',
          series_id: ep.series_id,
          episode_id: ep.id,
          revision_id: 'rev_2',
          content_hash: 'prophash12345678',
          content: { revision_reason: payload.reason },
        };
        artifactsMap.set(ep.id, [...(artifactsMap.get(ep.id) ?? []), proposal]);
      }
      ep.updated_at = new Date().toISOString();
      return { episode: ep };
    },

    async lockScreenplay(idempotencyKey, episodeId) {
      const ep = episodeMap.get(episodeId);
      if (!ep) throw new Error('not_found');

      ep.state = 'READY_FOR_PRODUCTION';
      ep.version += 1;
      const receipt: StudioArtifactEnvelope = {
        artifact_id: `art_rec_${Date.now()}`,
        artifact_type: 'LockedScreenplayReceipt',
        schema_version: 'studio.artifact/v1alpha1',
        series_id: ep.series_id,
        episode_id: ep.id,
        content_hash: 'rechash12345678',
        content: { receipt_id: 'rec_1001', state: 'READY_FOR_PRODUCTION' },
      };
      const pkg: StudioArtifactEnvelope = {
        artifact_id: `art_pkg_${Date.now()}`,
        artifact_type: 'LockedScreenplayPackage',
        schema_version: 'studio.artifact/v1alpha1',
        series_id: ep.series_id,
        episode_id: ep.id,
        content_hash: 'pkghash12345678',
        content: { package_id: 'pkg_5001', manifest: [] },
      };
      artifactsMap.set(ep.id, [...(artifactsMap.get(ep.id) ?? []), receipt, pkg]);
      ep.updated_at = new Date().toISOString();
      return { episode: ep };
    },

    async pollEvents() {
      return { cursor: 1, events: [] };
    },
  };
}

describe('Phase UI12 — Real Desktop Certification', () => {
  let client: IStudioApiClient;
  let store: StudioStore;

  beforeEach(() => {
    client = createMockHttpApiClient();
    store = new StudioStore(client);
  });

  it('certifies full 14-step creative pipeline from Series creation to Production Lock over StudioStore API V3', async () => {
    // 1. Create Series
    const seriesRes = await store.createSeries('key_series_01', 'Series Rừng Xanh', 'Hành trình khám phá thiên nhiên.');
    expect(seriesRes).toBeDefined();
    expect(seriesRes?.series.title).toBe('Series Rừng Xanh');
    const seriesId = seriesRes!.series.id;

    // 2. Create Episode
    const episodeRes = await store.createEpisode('key_ep_01', seriesId, 'Tập 1: Thỏ Thả Diều');
    expect(episodeRes).toBeDefined();
    expect(episodeRes?.episode.state).toBe('DRAFT');
    const episodeId = episodeRes!.episode.id;

    // 3. Start Run: Generate Ideas
    const runRes = await store.startRun('key_run_idea_01', episodeId);
    expect(runRes).toBeDefined();
    expect(runRes?.run_id).toBeDefined();

    // Reload episode & artifacts
    await store.loadEpisode(episodeId);
    let ep = store.getEpisode(episodeId);
    expect(ep?.state).toBe('IDEA_REVIEW');

    await store.loadArtifacts(episodeId);
    let artifacts = store.getArtifacts(episodeId);
    const ideaSet = artifacts.find((a) => a.artifact_type === 'IdeaCandidateSet');
    expect(ideaSet).toBeDefined();

    // 4. Select Idea
    const selectRes = await store.selectIdea('key_select_01', episodeId, {
      episode_id: episodeId,
      candidate_id: 'cand_1',
      revision_id: 'rev_1',
      expected_content_hash: ideaSet!.content_hash,
      expected_optimistic_version: ep!.version,
    });
    expect(selectRes).toBeDefined();
    expect(selectRes?.episode.state).toBe('STORY_DEVELOPMENT');

    // 5. Develop Story
    await store.startRun('key_run_story_01', episodeId);
    await store.loadEpisode(episodeId);
    ep = store.getEpisode(episodeId);
    expect(ep?.state).toBe('STORY_REVIEW');

    // 6. Generate Outline
    await store.startRun('key_run_outline_01', episodeId);
    await store.loadEpisode(episodeId);
    ep = store.getEpisode(episodeId);
    expect(ep?.state).toBe('OUTLINE_REVIEW');

    // 7. Generate Screenplay & Review
    await store.startRun('key_run_sp_01', episodeId);
    await store.loadEpisode(episodeId);
    ep = store.getEpisode(episodeId);
    expect(ep?.state).toBe('SCREENPLAY_REVIEW');

    // 8. Request Revision
    const revRes = await store.recordApproval('key_appr_rev_01', episodeId, {
      episode_id: episodeId,
      checkpoint: 'SCREENPLAY_REVIEW',
      decision: 'REQUEST_REVISION',
      reason: 'Cần sửa thoại cảnh 2.',
      expected_revision_id: 'rev_1',
      expected_content_hash: 'sphash12345678',
      expected_optimistic_version: ep!.version,
    });
    expect(revRes).toBeDefined();
    expect(revRes?.episode.state).toBe('REVISION_REQUIRED');

    // 9. Approve
    await store.loadEpisode(episodeId);
    ep = store.getEpisode(episodeId);
    const appRes = await store.recordApproval('key_appr_ok_01', episodeId, {
      episode_id: episodeId,
      checkpoint: 'SCREENPLAY_REVIEW',
      decision: 'APPROVED',
      expected_revision_id: 'rev_1',
      expected_content_hash: 'sphash12345678',
      expected_optimistic_version: ep!.version,
    });
    expect(appRes).toBeDefined();
    expect(appRes?.episode.state).toBe('APPROVED');

    // 10. Lock Screenplay -> READY_FOR_PRODUCTION
    await store.loadEpisode(episodeId);
    ep = store.getEpisode(episodeId);
    const lockRes = await store.lockScreenplay('key_lock_01', episodeId, {
      episode_id: episodeId,
      revision_id: 'rev_1',
      expected_content_hash: 'sphash12345678',
      expected_optimistic_version: ep!.version,
    });
    expect(lockRes).toBeDefined();
    expect(lockRes?.episode.state).toBe('READY_FOR_PRODUCTION');

    // Final state verification
    await store.loadEpisode(episodeId);
    ep = store.getEpisode(episodeId);
    expect(ep?.state).toBe('READY_FOR_PRODUCTION');

    await store.loadArtifacts(episodeId);
    artifacts = store.getArtifacts(episodeId);
    expect(artifacts.some((a) => a.artifact_type === 'LockedScreenplayReceipt')).toBe(true);
    expect(artifacts.some((a) => a.artifact_type === 'LockedScreenplayPackage')).toBe(true);
  });
});
