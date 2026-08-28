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

function mapStateToCheckpoint(state?: string, awaiting?: string | null): string {
  if (awaiting) return String(awaiting);
  const s = String(state || '').toUpperCase();
  if (s === 'IDEA_REVIEW') return 'IDEA';
  if (s === 'STORY_BIBLE_REVIEW') return 'STORY_BIBLE';
  if (s === 'OUTLINE_REVIEW') return 'OUTLINE';
  if (s === 'SCREENPLAY_REVIEW' || s === 'REVISING') return 'SCREENPLAY';
  if (s === 'LOCKED') return 'LOCKED';
  if (s === 'READY_FOR_PRODUCTION') return 'READY_FOR_PRODUCTION';
  return 'IDEA';
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
              const rawState = String(ep.state || 'DRAFT');
              // Preserve real fields; do NOT fabricate timestamps — leave undefined if missing so UI shows "—"
              const item: any = {
                ...ep,
                id: String(ep.id),
                project_id: String(ep.series_id || s.id),
                title: String(ep.title || ''),
                episode_number: Number(ep.episode_number ?? 1),
                state: rawState,
                current_checkpoint: mapStateToCheckpoint(rawState, ep.awaiting_checkpoint),
                version: Number(ep.optimistic_version ?? ep.version ?? 1),
                created_at: ep.created_at ? String(ep.created_at) : undefined,
                updated_at: ep.updated_at ? String(ep.updated_at) : undefined,
                metadata: (ep.metadata || {}) as Record<string, unknown>,
                awaiting_checkpoint: ep.awaiting_checkpoint ? String(ep.awaiting_checkpoint) : null,
                active_run_id: ep.active_run_id ? String(ep.active_run_id) : null,
                current_revision_id: ep.current_revision_id ? String(ep.current_revision_id) : null,
                artifact_summary: ep.artifact_summary ?? null,
                episode_url: ep.episode_url ?? null,
                run_url: ep.run_url ?? null,
              };
              // Derive description from metadata if available (real DB may store brief in metadata)
              const meta: any = item.metadata || {};
              const desc = meta.description || meta.brief || meta.synopsis || meta.summary || null;
              if (desc && !item.description) item.description = String(desc);
              // Derive progress_percent truthfully from state if server did not provide
              if (item.progress_percent == null) {
                const { getStageProgress } = await import('../model/types');
                item.progress_percent = getStageProgress(rawState);
              }
              studioEpisodes.push(item as EpisodeResource);
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
        filtered = filtered.filter((e: any) => {
          const title = String(e.title || '').toLowerCase();
          const desc = String(e.description || '').toLowerCase();
          const metaDesc = String((e.metadata as any)?.description || '').toLowerCase();
          return title.includes(q) || desc.includes(q) || metaDesc.includes(q);
        });
      }
      if (options?.state && options.state !== 'ALL') {
        const f = String(options.state).toUpperCase();
        filtered = filtered.filter((e: any) => {
          const st = String(e.state || '').toUpperCase();
          // Allow grouped filter: e.g., filter "SCREENPLAY" matches "SCREENPLAY_REVIEW"
          if (f === st) return true;
          if (f === 'IDEA' && st === 'IDEA_REVIEW') return true;
          if (f === 'STORY_BIBLE' && st === 'STORY_BIBLE_REVIEW') return true;
          if (f === 'OUTLINE' && st === 'OUTLINE_REVIEW') return true;
          if (f === 'SCREENPLAY' && (st === 'SCREENPLAY_REVIEW' || st === 'REVISING')) return true;
          return false;
        });
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
