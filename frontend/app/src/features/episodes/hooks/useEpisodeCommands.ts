/**
 * Mutation hooks for episode pipeline commands with version verification.
 */

import { useMutation, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';
import { EPISODE_DETAIL_QUERY_KEY } from './useEpisode';
import { EPISODE_ARTIFACTS_QUERY_KEY, EPISODE_RUNS_QUERY_KEY } from './useEpisodeArtifacts';
import { EPISODES_QUERY_KEY } from './useEpisodes';

export interface SelectIdeaInput {
  candidate_id?: string;
  idea_id?: string;
  revision_id?: string;
  expected_content_hash?: string;
  expected_version?: number;
  expected_optimistic_version?: number;
}

export interface CheckpointDecisionInput {
  decision: 'APPROVED' | 'REVISE' | 'REJECTED' | string;
  revision_id?: string;
  checkpoint?: string;
  artifact_hash?: string;
  feedback?: string;
  reason?: string;
  expected_version?: number;
  expected_optimistic_version?: number;
  actor?: string;
}

export interface LockScreenplayInput {
  revision_id: string;
  content_hash?: string;
  expected_content_hash?: string;
  expected_version?: number;
  expected_optimistic_version?: number;
}

export interface DeriveRevisionInput {
  series_id: string;
  parent_revision_id: string;
  new_content_hash: string;
  summary: string;
  invalidation_intent?: string | null;
  expected_version?: number;
  expected_optimistic_version?: number;
  actor?: string;
}

export function useEpisodeCommands(episodeId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: EPISODE_DETAIL_QUERY_KEY(episodeId) });
    queryClient.invalidateQueries({ queryKey: EPISODE_ARTIFACTS_QUERY_KEY(episodeId) });
    queryClient.invalidateQueries({ queryKey: EPISODE_RUNS_QUERY_KEY(episodeId) });
    queryClient.invalidateQueries({ queryKey: EPISODES_QUERY_KEY });
  };

  // Start / Resume Run
  const startRunMutation = useMutation<any, { idempotencyKey?: string } | void, Error>({
    mutationFn: async (data) => {
      const key = (data && data.idempotencyKey) || crypto.randomUUID();
      return client.studio.startRun(episodeId, key);
    },
    onSuccess: () => {
      invalidateAll();
    },
  });

  // Select Idea Candidate
  const selectIdeaMutation = useMutation<any, SelectIdeaInput, Error>({
    mutationFn: async (data) => {
      const candidateId = data.candidate_id || data.idea_id || '';
      const contentHash = data.expected_content_hash || '';
      const revId = data.revision_id || '';
      const version = data.expected_optimistic_version ?? data.expected_version;
      const key = crypto.randomUUID();
      return client.studio.selectIdea(
        episodeId,
        {
          episode_id: episodeId,
          revision_id: revId,
          candidate_id: candidateId,
          expected_content_hash: contentHash,
          expected_optimistic_version: version,
        },
        key,
      );
    },
    onSuccess: () => {
      invalidateAll();
    },
  });

  // Submit Checkpoint Decision / Approval
  const decisionMutation = useMutation<any, CheckpointDecisionInput, Error>({
    mutationFn: async (data) => {
      const key = crypto.randomUUID();
      const version = data.expected_optimistic_version ?? data.expected_version;
      return client.studio.recordApproval(
        episodeId,
        {
          episode_id: episodeId,
          revision_id: data.revision_id || '',
          checkpoint: data.checkpoint || 'SCREENPLAY',
          artifact_hash: data.artifact_hash || '',
          decision: data.decision,
          reason: data.reason || data.feedback || '',
          expected_optimistic_version: version,
        },
        key,
        data.actor || 'human_user',
      );
    },
    onSuccess: () => {
      invalidateAll();
    },
  });

  // Lock Screenplay
  const lockMutation = useMutation<any, LockScreenplayInput, Error>({
    mutationFn: async (data) => {
      const key = crypto.randomUUID();
      const hash = data.expected_content_hash || data.content_hash || '';
      const version = data.expected_optimistic_version ?? data.expected_version;
      return client.studio.lockScreenplay(
        episodeId,
        {
          episode_id: episodeId,
          revision_id: data.revision_id,
          expected_content_hash: hash,
          expected_optimistic_version: version,
        },
        key,
      );
    },
    onSuccess: () => {
      invalidateAll();
    },
  });

  // Derive Revision
  const deriveRevisionMutation = useMutation<any, DeriveRevisionInput, Error>({
    mutationFn: async (data) => {
      const key = crypto.randomUUID();
      const version = data.expected_optimistic_version ?? data.expected_version;
      return client.studio.deriveRevision(
        episodeId,
        {
          episode_id: episodeId,
          series_id: data.series_id,
          parent_revision_id: data.parent_revision_id,
          new_content_hash: data.new_content_hash,
          summary: data.summary,
          invalidation_intent: data.invalidation_intent,
          expected_optimistic_version: version,
        },
        key,
        data.actor || 'human_user',
      );
    },
    onSuccess: () => {
      invalidateAll();
    },
  });

  return {
    startRun: startRunMutation.mutateAsync,
    startGeneration: startRunMutation.mutateAsync,
    isGenerating: startRunMutation.isLoading,
    selectIdea: selectIdeaMutation.mutateAsync,
    isSelectingIdea: selectIdeaMutation.isLoading,
    submitDecision: decisionMutation.mutateAsync,
    isSubmittingDecision: decisionMutation.isLoading,
    lockScreenplay: lockMutation.mutateAsync,
    isLocking: lockMutation.isLoading,
    deriveRevision: deriveRevisionMutation.mutateAsync,
    isDerivingRevision: deriveRevisionMutation.isLoading,
    error:
      startRunMutation.error ||
      selectIdeaMutation.error ||
      decisionMutation.error ||
      lockMutation.error ||
      deriveRevisionMutation.error,
  };
}

