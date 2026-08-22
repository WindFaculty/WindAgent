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

/**
 * P0.8 canonical-only: episode creation goes through the Studio command API.
 * No legacy fallback — a failed studio create is a failed mutation.
 */
export function useCreateEpisode() {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const mutation = useMutation<EpisodeResource, CreateEpisodeInput, Error>({
    mutationFn: async ({ projectId, title, episode_number }: CreateEpisodeInput) => {
      const idempotencyKey = crypto.randomUUID();
      const res = await client.studio.createEpisode(
        projectId,
        {
          series_id: projectId,
          title,
          episode_number: episode_number || 1,
        },
        idempotencyKey,
      );
      return {
        id: res.episode_id,
        project_id: res.series_id || projectId,
        title,
        episode_number: episode_number || 1,
        state: res.state || 'DRAFT',
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      } as EpisodeResource;
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
