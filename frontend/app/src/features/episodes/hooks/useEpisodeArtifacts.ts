/**
 * Hook to query episode artifacts and execution runs.
 */

import { useQuery, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';
import type { EpisodeArtifactEnvelope, PipelineRun } from '@windagent/api-contracts';

export const EPISODE_ARTIFACTS_QUERY_KEY = (id: string) => ['v3', 'episodes', id, 'artifacts'];
export const EPISODE_RUNS_QUERY_KEY = (id: string) => ['v3', 'episodes', id, 'runs'];

export function useEpisodeArtifacts(episodeId?: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const artifactsQuery = useQuery<EpisodeArtifactEnvelope[], Error>({
    queryKey: EPISODE_ARTIFACTS_QUERY_KEY(episodeId ?? ''),
    queryFn: async () => {
      if (!episodeId) return [];
      // P0.7: canonical content-addressed studio artifacts (real revision
      // authority + content_hash), not the legacy demo namespace.
      const rows = await client.studio.listEpisodeArtifacts(episodeId);
      return rows.map((a: any) => ({
        artifact_id: String(a.artifact_id ?? ''),
        episode_id: String(a.episode_id ?? episodeId),
        kind: String(a.artifact_type ?? a.kind ?? ''),
        revision_id: a.revision_id ? String(a.revision_id) : '',
        content: (a.content ?? {}) as Record<string, any>,
        created_at: String(a.created_at ?? ''),
        ...a,
      })) as EpisodeArtifactEnvelope[];
    },
    enabled: Boolean(episodeId),
    staleTimeMs: 10000,
  });

  const runsQuery = useQuery<PipelineRun[], Error>({
    queryKey: EPISODE_RUNS_QUERY_KEY(episodeId ?? ''),
    queryFn: async () => {
      if (!episodeId) return [];
      return client.episodes.getRuns(episodeId);
    },
    enabled: Boolean(episodeId),
    staleTimeMs: 10000,
  });

  const invalidate = () => {
    if (episodeId) {
      queryClient.invalidateQueries({ queryKey: EPISODE_ARTIFACTS_QUERY_KEY(episodeId) });
      queryClient.invalidateQueries({ queryKey: EPISODE_RUNS_QUERY_KEY(episodeId) });
    }
  };

  const latestIdeaSet = artifactsQuery.data?.find((a: any) => a.kind === 'IdeaCandidateSet');
  const latestStoryBible = artifactsQuery.data?.find((a: any) => a.kind === 'StoryBible');
  const latestOutline = artifactsQuery.data?.find((a: any) => a.kind === 'EpisodeOutline');
  const latestScreenplay = artifactsQuery.data?.find((a: any) => a.kind === 'ScreenplayDraft');

  return {
    artifacts: artifactsQuery.data ?? [],
    runs: runsQuery.data ?? [],
    latestIdeaSet,
    latestStoryBible,
    latestOutline,
    latestScreenplay,
    isLoading: artifactsQuery.isLoading || runsQuery.isLoading,
    isError: artifactsQuery.isError || runsQuery.isError,
    error: artifactsQuery.error || runsQuery.error,
    refetch: () => {
      artifactsQuery.refetch();
      runsQuery.refetch();
    },
    invalidate,
  };
}
