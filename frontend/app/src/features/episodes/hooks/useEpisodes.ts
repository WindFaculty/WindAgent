/**
 * Hook to query all canonical episodes across projects.
 */

import { useQuery, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';
import type { EpisodeResource, CursorPage } from '@windagent/api-contracts';

export const EPISODES_QUERY_KEY = ['v3', 'episodes'];

export interface UseEpisodesOptions {
  projectId?: string;
  state?: string;
  search?: string;
  limit?: number;
}

export function useEpisodes(options?: UseEpisodesOptions) {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const query = useQuery<CursorPage<EpisodeResource>, Error>({
    queryKey: [...EPISODES_QUERY_KEY, options?.projectId ?? '', options?.state ?? 'ALL', options?.search ?? ''],
    queryFn: async () => {
      return client.episodes.listAll({
        project_id: options?.projectId,
        state: options?.state,
        search: options?.search,
        limit: options?.limit,
      });
    },
    staleTimeMs: 10000,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: EPISODES_QUERY_KEY });
  };

  return {
    episodes: query.data?.items ?? [],
    pageInfo: query.data?.page_info,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    invalidate,
  };
}
