/**
 * Hook to query and manage canonical Studio Series and summary metrics.
 */

import { useQuery, useMutation, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';
import type { StudioSeriesResource, StudioEpisodeResource } from '@windagent/api-contracts';

export const STUDIO_SERIES_QUERY_KEY = ['v3', 'studio', 'series'];

export interface CreateSeriesInput {
  title: string;
  description?: string;
  genre?: string;
  tone?: string;
  target_audience?: string;
  language?: string;
  narrative_style?: string;
}

export function useStudioSeries() {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const seriesQuery = useQuery<{ items: StudioSeriesResource[]; episodesBySeries: Record<string, StudioEpisodeResource[]> }, Error>({
    queryKey: STUDIO_SERIES_QUERY_KEY,
    queryFn: async () => {
      const res = await client.studio.listSeries();
      const items = (res.items || []) as StudioSeriesResource[];

      // Fetch episodes for all series to compute live, truthful metrics without stubs
      const episodesBySeries: Record<string, StudioEpisodeResource[]> = {};
      await Promise.all(
        items.map(async (s) => {
          try {
            const epRes = await client.studio.listEpisodes(s.id);
            episodesBySeries[s.id] = (epRes.items || []) as StudioEpisodeResource[];
          } catch {
            episodesBySeries[s.id] = [];
          }
        }),
      );

      return { items, episodesBySeries };
    },
    staleTimeMs: 10000,
  });

  const createSeriesMutation = useMutation<any, CreateSeriesInput, Error>({
    mutationFn: async (input) => {
      const idempotencyKey = crypto.randomUUID();
      const metadata: Record<string, unknown> = {
        genre: input.genre || 'Sci-Fi',
        tone: input.tone || 'Cinematic',
        target_audience: input.target_audience || '13-17',
        language: input.language || 'vi',
      };
      if (input.narrative_style) {
        metadata.narrative_style = input.narrative_style;
      }
      return client.studio.createSeries(
        {
          title: input.title,
          description: input.description || '',
          metadata,
        },
        idempotencyKey,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: STUDIO_SERIES_QUERY_KEY });
    },
  });

  const seriesList = seriesQuery.data?.items ?? [];
  const episodesMap = seriesQuery.data?.episodesBySeries ?? {};

  // Flatten all episodes across series for real, truthful metrics
  const allEpisodes = Object.values(episodesMap).flat();

  const metrics = {
    totalSeries: seriesList.length,
    activeSeries: seriesList.length,
    episodesInProgress: allEpisodes.filter((ep) =>
      ['DRAFT', 'IDEA_REVIEW', 'STORY_BIBLE_REVIEW', 'OUTLINE_REVIEW', 'SCREENPLAY_REVIEW', 'REVISING'].includes(ep.state),
    ).length,
    pendingApproval: allEpisodes.filter(
      (ep) => Boolean(ep.awaiting_checkpoint) || ['IDEA_REVIEW', 'STORY_BIBLE_REVIEW', 'OUTLINE_REVIEW', 'SCREENPLAY_REVIEW'].includes(ep.state),
    ).length,
    readyForProduction: allEpisodes.filter((ep) => ['READY_FOR_PRODUCTION', 'LOCKED'].includes(ep.state)).length,
  };

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: STUDIO_SERIES_QUERY_KEY });
  };

  return {
    series: seriesList,
    episodesMap,
    allEpisodes,
    metrics,
    isLoading: seriesQuery.isLoading,
    isError: seriesQuery.isError,
    error: seriesQuery.error,
    createSeries: createSeriesMutation.mutateAsync,
    isCreating: createSeriesMutation.isLoading,
    createError: createSeriesMutation.error,
    refetch: seriesQuery.refetch,
    invalidate,
  };
}
