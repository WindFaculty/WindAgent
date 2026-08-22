/**
 * Hook to query single episode detail.
 */

import { useQuery, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';
import type { EpisodeResource } from '@windagent/api-contracts';

export const EPISODE_DETAIL_QUERY_KEY = (id: string) => ['v3', 'episodes', id];

function mapStateToCheckpoint(awaiting?: string | null, state?: string): string {
  if (awaiting) return awaiting;
  switch (state) {
    case 'IDEA_REVIEW':
      return 'IDEA';
    case 'STORY_BIBLE_REVIEW':
      return 'STORY_BIBLE';
    case 'OUTLINE_REVIEW':
      return 'OUTLINE';
    case 'SCREENPLAY_REVIEW':
    case 'REVISING':
      return 'SCREENPLAY';
    case 'LOCKED':
      return 'LOCKED';
    case 'READY_FOR_PRODUCTION':
      return 'READY_FOR_PRODUCTION';
    default:
      return 'IDEA';
  }
}

export function useEpisode(episodeId?: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const query = useQuery<EpisodeResource, Error>({
    queryKey: EPISODE_DETAIL_QUERY_KEY(episodeId ?? ''),
    queryFn: async () => {
      if (!episodeId) throw new Error('Episode ID is required');
      // P0.7: Canonical Studio authority (/api/v3/studio/episodes/{id})
      const raw: any = await client.studio.getEpisode(episodeId);
      const mapped: EpisodeResource = {
        id: String(raw.id || raw.episode_id || episodeId),
        project_id: String(raw.series_id || raw.project_id || ''),
        episode_number: Number(raw.episode_number ?? 1),
        title: String(raw.title || ''),
        state: String(raw.state || 'DRAFT') as any,
        current_checkpoint: mapStateToCheckpoint(raw.awaiting_checkpoint, raw.state) as any,
        current_revision_id: raw.current_revision_id ? String(raw.current_revision_id) : null,
        version: Number(raw.optimistic_version ?? raw.version ?? 1),
        created_at: String(raw.created_at || new Date().toISOString()),
        updated_at: String(raw.updated_at || new Date().toISOString()),
        metadata: (raw.metadata || {}) as Record<string, unknown>,
        ...raw,
      };
      return mapped;
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

