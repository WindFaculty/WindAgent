import { useQuery, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';

import type { ProjectResource, EpisodeResource, CursorPage } from '@windagent/api-contracts';

export const PROJECT_QUERY_KEY = (id: string) => ['v3', 'projects', id];
export const PROJECT_EPISODES_QUERY_KEY = (id: string) => ['v3', 'projects', id, 'episodes'];

export function useProject(projectId?: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const projectQuery = useQuery<ProjectResource, Error>({
    queryKey: PROJECT_QUERY_KEY(projectId ?? ''),
    queryFn: async () => {
      if (!projectId) throw new Error('Project ID is required');
      return client.projects.get(projectId);
    },
    enabled: Boolean(projectId),
    staleTimeMs: 10000,
  });

  const episodesQuery = useQuery<CursorPage<EpisodeResource>, Error>({
    queryKey: PROJECT_EPISODES_QUERY_KEY(projectId ?? ''),
    queryFn: async () => {
      if (!projectId) throw new Error('Project ID is required');
      return client.episodes.list(projectId);
    },
    enabled: Boolean(projectId),
    staleTimeMs: 10000,
  });


  const invalidate = () => {
    if (projectId) {
      queryClient.invalidateQueries({ queryKey: PROJECT_QUERY_KEY(projectId) });
      queryClient.invalidateQueries({ queryKey: PROJECT_EPISODES_QUERY_KEY(projectId) });
    }
  };

  return {
    project: projectQuery.data ?? null,
    episodes: episodesQuery.data?.items ?? [],
    isLoading: projectQuery.isLoading || episodesQuery.isLoading,
    isError: projectQuery.isError || episodesQuery.isError,
    error: projectQuery.error || episodesQuery.error,
    refetch: () => {
      projectQuery.refetch();
      episodesQuery.refetch();
    },
    invalidate,
  };
}
