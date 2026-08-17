/**
 * Hook to query single episode detail.
 */

import { useQuery, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';
import type { EpisodeResource } from '@windagent/api-contracts';

export const EPISODE_DETAIL_QUERY_KEY = (id: string) => ['v3', 'episodes', id];

export function useEpisode(episodeId?: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const query = useQuery<EpisodeResource, Error>({
    queryKey: EPISODE_DETAIL_QUERY_KEY(episodeId ?? ''),
    queryFn: async () => {
      if (!episodeId) throw new Error('Episode ID is required');
      return client.episodes.get(episodeId);
    },
    enabled: Boolean(episodeId),
    staleTimeMs: 10000,
  });

  const invalidate = () => {
    if (episodeId) {
      queryClient.invalidateQueries({ queryKey: EPISODE_DETAIL_QUERY_KEY(episodeId) });
    }
  };

  return {
    episode: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    invalidate,
  };
}
