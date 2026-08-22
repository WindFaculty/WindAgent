import { useQuery, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';

import type { ProjectResource, EpisodeResource, CursorPage } from '@windagent/api-contracts';

export const PROJECT_QUERY_KEY = (id: string) => ['v3', 'projects', id];
export const PROJECT_EPISODES_QUERY_KEY = (id: string) => ['v3', 'projects', id, 'episodes'];

/**
 * P0.8 canonical-only: single authority = Studio API (/api/v3/studio).
 * No silent legacy fallback — failures surface as query errors.
 */
export function useProject(projectId?: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const projectQuery = useQuery<ProjectResource, Error>({
    queryKey: PROJECT_QUERY_KEY(projectId ?? ''),
    queryFn: async () => {
      if (!projectId) throw new Error('Project ID is required');
      const s: any = await client.studio.getSeries(projectId);
      if (!s || !s.id) throw new Error(`Series '${projectId}' not found.`);
      return {
        id: s.id,
        name: s.title,
        description: s.description,
        episodes_count: s.episode_count ?? s.episode_ids?.length ?? 0,
        metadata: s.metadata || {},
        version: s.optimistic_version ?? 1,
        created_at: s.created_at || new Date().toISOString(),
        updated_at: s.updated_at || new Date().toISOString(),
      } as ProjectResource;
    },
    enabled: Boolean(projectId),
    staleTimeMs: 10000,
  });

  const episodesQuery = useQuery<CursorPage<EpisodeResource>, Error>({
    queryKey: PROJECT_EPISODES_QUERY_KEY(projectId ?? ''),
    queryFn: async () => {
      if (!projectId) throw new Error('Project ID is required');
      const epRes: any = await client.studio.listEpisodes(projectId);
      const items = ((epRes && Array.isArray(epRes.items)) ? epRes.items : []).map((ep: any) => ({
        id: ep.id,
        project_id: ep.series_id || projectId,
        episode_number: ep.episode_number ?? 1,
        title: ep.title,
        state: ep.state,
        version: ep.optimistic_version ?? ep.version ?? 1,
        created_at: ep.created_at || new Date().toISOString(),
        updated_at: ep.updated_at || new Date().toISOString(),
        metadata: ep.metadata || {},
      })) as EpisodeResource[];
      return { items, page_info: { next_cursor: null, has_more: false, total_count: items.length } };
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
