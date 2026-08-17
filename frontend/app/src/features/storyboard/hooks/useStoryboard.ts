/**
 * Phase 9C — Storyboard Feature Hooks
 * Real generation tracking via server-issued generation_id. No fake setTimeout timers.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { useApiClient } from '@windagent/app/src/shared/hooks/useApiClient';
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
    mutationFn: (data: { episodeId: string; title: string; script_text?: string; location?: string; character_ids?: string[]; source_screenplay_revision_id?: string }) =>
      client.storyboard.createScene(data),
    onSuccess: (_result, vars) => {
      queryClient.invalidateQueries({ queryKey: storyboardKeys.scenes(vars.episodeId) });
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
 * Storyboard realtime WebSocket hook.
 * Subscribes to /ws/v3/storyboard/{episodeId} and invalidates scenes on generation events.
 */
export function useStoryboardRealtime(episodeId: string, apiBaseUrl: string) {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!episodeId || !apiBaseUrl) return;
    const wsUrl = apiBaseUrl.replace(/^http/, 'ws') + `/ws/v3/storyboard/${episodeId}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data);
        if (evt.event === 'generation.completed' || evt.event === 'generation.failed') {
          queryClient.invalidateQueries({ queryKey: storyboardKeys.scenes(episodeId) });
          queryClient.invalidateQueries({ queryKey: storyboardKeys.board(episodeId) });
        } else if (evt.event === 'storyboard.snapshot' || evt.event === 'scene.updated') {
          queryClient.invalidateQueries({ queryKey: storyboardKeys.scenes(episodeId) });
        }
      } catch {
        // ignore malformed messages
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [episodeId, apiBaseUrl, queryClient]);
}
