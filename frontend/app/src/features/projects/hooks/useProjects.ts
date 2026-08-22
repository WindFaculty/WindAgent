import { useQuery, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';

import type { ProjectResource, CursorPage } from '@windagent/api-contracts';

export const PROJECTS_QUERY_KEY = ['v3', 'projects'];

export interface UseProjectsOptions {
  search?: string;
  genre?: string;
  cursor?: string;
  limit?: number;
}

/**
 * P0.8 canonical-only: single authority = Studio Series (/api/v3/studio/series).
 * No legacy projects merge — the studio surface is the only project catalog.
 */
export function useProjects(options?: UseProjectsOptions) {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const query = useQuery<CursorPage<ProjectResource>, Error>({
    queryKey: [...PROJECTS_QUERY_KEY, options?.search ?? '', options?.genre ?? 'all'],
    queryFn: async () => {
      const sRes = await client.studio.listSeries();
      let items: ProjectResource[] = ((sRes && Array.isArray(sRes.items)) ? sRes.items : []).map((s: any) => ({
        id: s.id,
        name: s.title,
        description: s.description,
        episodes_count: s.episode_count ?? s.episode_ids?.length ?? 0,
        metadata: s.metadata || {},
        version: s.optimistic_version ?? 1,
        created_at: s.created_at || new Date().toISOString(),
        updated_at: s.updated_at || new Date().toISOString(),
      })) as ProjectResource[];

      if (options?.search) {
        const q = options.search.toLowerCase();
        items = items.filter((p) => p.name.toLowerCase().includes(q) || (p.description && p.description.toLowerCase().includes(q)));
      }
      if (options?.genre && options.genre !== 'all') {
        items = items.filter((p) => (p.metadata?.genre as string)?.toLowerCase() === options.genre?.toLowerCase());
      }

      return {
        items,
        page_info: {
          next_cursor: null,
          has_more: false,
          total_count: items.length,
        },
      };
    },
    staleTimeMs: 10000,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY });
  };

  return {
    projects: query.data?.items ?? [],
    pageInfo: query.data?.page_info,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    invalidate,
  };
}
