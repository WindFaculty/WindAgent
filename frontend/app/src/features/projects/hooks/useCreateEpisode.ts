import { useMutation, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';
import { PROJECT_EPISODES_QUERY_KEY, PROJECT_QUERY_KEY } from './useProject';
import { PROJECTS_QUERY_KEY } from './useProjects';
import type { EpisodeResource } from '@windagent/api-contracts';

export interface CreateEpisodeInput {
  projectId: string;
  title: string;
  episode_number?: number;
}

export function useCreateEpisode() {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const mutation = useMutation<EpisodeResource, CreateEpisodeInput, Error>({
    mutationFn: async ({ projectId, title, episode_number }: CreateEpisodeInput) => {
      const idempotencyKey = crypto.randomUUID();
      return client.episodes.create(projectId, { title, episode_number }, idempotencyKey);
    },
    onSuccess: (_data: EpisodeResource, variables: CreateEpisodeInput) => {
      queryClient.invalidateQueries({ queryKey: PROJECT_QUERY_KEY(variables.projectId) });
      queryClient.invalidateQueries({ queryKey: PROJECT_EPISODES_QUERY_KEY(variables.projectId) });
      queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY });
    },
  });


  return {
    createEpisode: mutation.mutateAsync,
    isCreating: mutation.isLoading,
    isError: Boolean(mutation.error),
    error: mutation.error,
  };
}

