/**
 * Hook to query all canonical episodes across projects.
 * P0.8 canonical-only: single authority = Studio API (/api/v3/studio).
 * No legacy fallback — if the studio surface fails, the query fails honestly.
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
      const seriesListRes = await client.studio.listSeries();
      const sList = (seriesListRes.items || []) as any[];
      const studioEpisodes: EpisodeResource[] = [];
      await Promise.all(
        sList.map(async (s) => {
          if (options?.projectId && options.projectId !== s.id) return;
          try {
            const epRes = await client.studio.listEpisodes(s.id);
            for (const ep of (epRes.items || []) as any[]) {
              studioEpisodes.push({
                id: ep.id,
                project_id: ep.series_id || s.id,
                title: ep.title,
                episode_number: ep.episode_number ?? 1,
                state: ep.state,
                current_checkpoint: ep.awaiting_checkpoint || ep.state,
                version: ep.optimistic_version ?? ep.version ?? 1,
                created_at: ep.created_at || new Date().toISOString(),
                updated_at: ep.updated_at || new Date().toISOString(),
                metadata: ep.metadata || {},
              } as EpisodeResource);
            }
          } catch {
            // one unreadable series must not hide the rest; its episodes are
            // simply absent (server-side list is still the only authority)
          }
        }),
      );

      let filtered = studioEpisodes;
      if (options?.search) {
        const q = options.search.toLowerCase();
        filtered = filtered.filter((e) => e.title.toLowerCase().includes(q));
      }
      if (options?.state && options.state !== 'ALL') {
        filtered = filtered.filter((e) => e.state?.toUpperCase() === options.state?.toUpperCase());
      }

      return {
        items: filtered,
        page_info: {
          next_cursor: null,
          has_more: false,
          total_count: filtered.length,
        },
      };
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
