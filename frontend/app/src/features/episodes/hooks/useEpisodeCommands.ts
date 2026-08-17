/**
 * Mutation hooks for episode pipeline commands with version verification.
 */

import { useMutation, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';
import { EPISODE_DETAIL_QUERY_KEY } from './useEpisode';
import { EPISODE_ARTIFACTS_QUERY_KEY, EPISODE_RUNS_QUERY_KEY } from './useEpisodeArtifacts';
import { EPISODES_QUERY_KEY } from './useEpisodes';
import type { EpisodeResource, PipelineRun } from '@windagent/api-contracts';

export interface SelectIdeaInput {
  episodeId: string;
  idea_id: string;
  expected_version: number;
}

export interface CheckpointDecisionInput {
  episodeId: string;
  decision: 'APPROVED' | 'REVISE' | 'REJECTED';
  revision_id: string;
  feedback?: string;
  expected_version: number;
}

export interface LockScreenplayInput {
  episodeId: string;
  revision_id: string;
  content_hash: string;
  expected_version: number;
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

  // Start Generation
  const startGenMutation = useMutation<PipelineRun, { checkpoint?: string; prompt_override?: string }, Error>({
    mutationFn: async (data) => {
      return client.episodes.startGeneration(episodeId, data);
    },
    onSuccess: () => {
      invalidateAll();
    },
  });

  // Select Idea
  const selectIdeaMutation = useMutation<EpisodeResource, { idea_id: string; expected_version: number }, Error>({
    mutationFn: async (data) => {
      return client.episodes.selectIdea(episodeId, data);
    },
    onSuccess: () => {
      invalidateAll();
    },
  });

  // Submit Checkpoint Decision
  const decisionMutation = useMutation<EpisodeResource, { decision: 'APPROVED' | 'REVISE' | 'REJECTED'; revision_id: string; feedback?: string; expected_version: number }, Error>({
    mutationFn: async (data) => {
      return client.episodes.submitDecision(episodeId, data);
    },
    onSuccess: () => {
      invalidateAll();
    },
  });

  // Lock Screenplay
  const lockMutation = useMutation<EpisodeResource, { revision_id: string; content_hash: string; expected_version: number }, Error>({
    mutationFn: async (data) => {
      return client.episodes.lockScreenplay(episodeId, data);
    },
    onSuccess: () => {
      invalidateAll();
    },
  });

  // Cancel Run
  const cancelMutation = useMutation<{ episode_id: string; status: string }, void, Error>({
    mutationFn: async () => {
      return client.episodes.cancelRun(episodeId);
    },
    onSuccess: () => {
      invalidateAll();
    },
  });

  return {
    startGeneration: startGenMutation.mutateAsync,
    isGenerating: startGenMutation.isLoading,
    selectIdea: selectIdeaMutation.mutateAsync,
    isSelectingIdea: selectIdeaMutation.isLoading,
    submitDecision: decisionMutation.mutateAsync,
    isSubmittingDecision: decisionMutation.isLoading,
    lockScreenplay: lockMutation.mutateAsync,
    isLocking: lockMutation.isLoading,
    cancelRun: cancelMutation.mutateAsync,
    isCancelling: cancelMutation.isLoading,
    error:
      startGenMutation.error ||
      selectIdeaMutation.error ||
      decisionMutation.error ||
      lockMutation.error ||
      cancelMutation.error,
  };
}
