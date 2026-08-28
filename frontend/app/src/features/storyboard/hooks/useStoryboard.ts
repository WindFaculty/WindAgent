/**
 * Phase 9C — Storyboard Feature Hooks
 * Real generation tracking via server-issued generation_id. No fake setTimeout timers.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import { useRealtimeClient } from '../../../realtime/RealtimeProvider';
import type { GenerationJobResource } from '@windagent/api-contracts';

export const storyboardKeys = {
  all: ['storyboard'] as const,
  board: (episodeId: string) => [...storyboardKeys.all, 'board', episodeId] as const,
  scenes: (episodeId: string) => [...storyboardKeys.all, 'scenes', episodeId] as const,
  job: (sceneId: string, jobId: string) => [...storyboardKeys.all, 'job', sceneId, jobId] as const,
};

export function useStoryboard(episodeId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: storyboardKeys.board(episodeId),
    queryFn: () => client.storyboard.getStoryboard(episodeId),
    enabled: Boolean(episodeId),
  });
}

export function useStoryboardScenes(episodeId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: storyboardKeys.scenes(episodeId),
    queryFn: () => client.storyboard.listScenes(episodeId),
    enabled: Boolean(episodeId),
  });
}

export function useSyncStoryboard(episodeId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => client.storyboard.syncFromScreenplay(episodeId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: storyboardKeys.board(episodeId) });
      queryClient.invalidateQueries({ queryKey: storyboardKeys.scenes(episodeId) });
    },
  });
}

export function useCreateScene() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { episodeId: string; storyboard_id: string; title: string; script_text?: string; location?: string; character_ids?: string[]; duration_seconds?: number; source_screenplay_revision_id?: string }) =>
      client.storyboard.createScene({ storyboard_id: data.storyboard_id, title: data.title, script_text: data.script_text, location: data.location, character_ids: data.character_ids, duration_seconds: data.duration_seconds, source_screenplay_revision_id: data.source_screenplay_revision_id }),
    onSuccess: (_result, vars) => {
      queryClient.invalidateQueries({ queryKey: storyboardKeys.scenes(vars.episodeId) });
      queryClient.invalidateQueries({ queryKey: storyboardKeys.board(vars.episodeId) });
    },
  });
}

export function useUpdateScene(episodeId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sceneId, ...data }: { sceneId: string; title?: string; script_text?: string; location?: string; character_ids?: string[]; expected_version: number }) =>
      client.storyboard.updateScene(sceneId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: storyboardKeys.scenes(episodeId) });
    },
  });
}

/**
 * Trigger concept art generation.
 * Returns a server-issued generation_id immediately — no fake timers.
 * Track progress with useGenerationJob.
 */
export function useTriggerGeneration(episodeId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sceneId, style_prompt, reference_character_ids }: { sceneId: string; style_prompt?: string; reference_character_ids?: string[] }) =>
      client.storyboard.triggerGeneration(sceneId, { style_prompt, reference_character_ids }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: storyboardKeys.scenes(episodeId) });
    },
  });
}

/**
 * Poll generation job status by generation_id.
 * Stops polling when job is terminal (COMPLETED | FAILED).
 */
export function useGenerationJob(sceneId: string, generationId: string | undefined) {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: storyboardKeys.job(sceneId, generationId ?? ''),
    queryFn: () => client.storyboard.getGenerationJob(sceneId, generationId!),
    enabled: Boolean(sceneId) && Boolean(generationId),
    refetchInterval: (query) => {
      const status = (query.state.data as GenerationJobResource | undefined)?.status;
      if (status === 'COMPLETED' || status === 'FAILED') return false;
      return 2000; // poll every 2s until terminal
    },
  });

  // Invalidate scenes when generation completes
  const prevStatus = useRef<string | undefined>(undefined);
  useEffect(() => {
    const status = query.data?.status;
    if (status !== prevStatus.current && (status === 'COMPLETED' || status === 'FAILED')) {
      queryClient.invalidateQueries({ queryKey: storyboardKeys.scenes(sceneId) });
    }
    prevStatus.current = status;
  }, [query.data?.status, queryClient, sceneId]);

  return query;
}

/**
 * Storyboard realtime hook via @windagent/realtime.
 * Subscribes to storyboard events for the episode and invalidates queries on generation updates.
 */
export function useStoryboardRealtime(episodeId: string, _apiBaseUrl?: string) {
  const queryClient = useQueryClient();
  const realtime = useRealtimeClient();

  useEffect(() => {
    if (!episodeId) return;

    const unsubscribe = realtime.subscribe(
      { aggregateType: 'storyboard', aggregateId: episodeId },
      (evt) => {
        const eventType = evt.event_type || (evt.payload as any)?.event;
        if (eventType === 'generation.completed' || eventType === 'generation.failed') {
          queryClient.invalidateQueries({ queryKey: storyboardKeys.scenes(episodeId) });
          queryClient.invalidateQueries({ queryKey: storyboardKeys.board(episodeId) });
        } else if (eventType === 'storyboard.snapshot' || eventType === 'scene.updated') {
          queryClient.invalidateQueries({ queryKey: storyboardKeys.scenes(episodeId) });
        }
      }
    );

    return () => {
      unsubscribe();
    };
  }, [episodeId, realtime, queryClient]);
}
