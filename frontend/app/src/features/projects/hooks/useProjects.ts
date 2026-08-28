import { useQuery, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';

import type { ProjectResource, CursorPage } from '@windagent/api-contracts';
import {
  computeProjectProgress,
  deriveProjectStatus,
  type DerivedStatus,
  type EpisodeStateInfo,
} from '../model/types';

export const PROJECTS_QUERY_KEY = ['v3', 'projects'];

export interface UseProjectsOptions {
  search?: string;
  genre?: string;
  cursor?: string;
  limit?: number;
}

/** Project enriched with real status/progress derived from its DB episodes. */
export interface ProjectListItem extends ProjectResource {
  derived_status: DerivedStatus;
  progress_percent: number;
  episodes: EpisodeStateInfo[];
}

/**
 * P0.8 canonical-only: single authority = Studio Series (/api/v3/studio/series).
 * Status/progress come from the real episode states persisted in the database
 * (fetched via /api/v3/studio/series/{id}/episodes) — no client-side fabrication.
 */
export function useProjects(options?: UseProjectsOptions) {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const query = useQuery<CursorPage<ProjectListItem>, Error>({
    queryKey: [...PROJECTS_QUERY_KEY, options?.search ?? '', options?.genre ?? 'all'],
    queryFn: async () => {
      const sRes = await client.studio.listSeries();
      const seriesList: any[] = (sRes && Array.isArray(sRes.items)) ? sRes.items : [];

      // Real episode states for every series (single parallel batch).
      const episodeLists = await Promise.all(
        seriesList.map(async (s): Promise<EpisodeStateInfo[]> => {
          try {
            const epRes: any = await client.studio.listEpisodes(s.id);
            const items = Array.isArray(epRes?.items) ? epRes.items : [];
            return items.map((ep: any) => ({
              id: ep.id,
              state: ep.state ?? null,
              active_run_id: ep.active_run_id ?? null,
              updated_at: ep.updated_at ?? null,
            }));
          } catch {
            return [];
          }
        }),
      );

      let items: ProjectListItem[] = seriesList.map((s, i) => {
        const episodes = episodeLists[i] ?? [];
        return {
          id: s.id,
          name: s.title,
          description: s.description,
          // The live episode list is the source of truth; the series counter
          // can drift, so keep whichever reports more (never fabricate).
          episodes_count: Math.max(s.episode_count ?? 0, s.episode_ids?.length ?? 0, episodes.length),
          metadata: s.metadata || {},
          version: s.optimistic_version ?? 1,
          created_at: s.created_at || '',
          updated_at: s.updated_at || '',
          derived_status: deriveProjectStatus(episodes),
          progress_percent: computeProjectProgress(episodes),
          episodes,
        };
      });

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
