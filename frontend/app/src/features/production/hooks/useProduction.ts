/**
 * Phase 10 — Production Feature Hooks
 * Authoritative production plan, shots, and stage jobs query & mutation hooks.
 * Includes WebSocket realtime hook for /ws/v3/production/{episodeId}.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import { useRealtimeClient } from '../../../realtime/RealtimeProvider';
import type { JobStage } from '@windagent/api-contracts';

export const productionKeys = {
  all: ['production'] as const,
  plan: (episodeId: string) => [...productionKeys.all, 'plan', episodeId] as const,
  shots: (episodeId: string) => [...productionKeys.all, 'shots', episodeId] as const,
  shot: (shotId: string) => [...productionKeys.all, 'shot', shotId] as const,
  jobs: (episodeId: string, stage?: string) => [...productionKeys.all, 'jobs', episodeId, stage ?? 'all'] as const,
  job: (jobId: string) => [...productionKeys.all, 'job', jobId] as const,
  delivery: (episodeId: string) => [...productionKeys.all, 'delivery', episodeId] as const,
};

export function useProductionPlan(episodeId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: productionKeys.plan(episodeId),
    queryFn: () => client.production.getPlan(episodeId),
    enabled: Boolean(episodeId),
  });
}

export function useCreateProductionPlan(episodeId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { screenplay_revision_id: string; storyboard_revision_id: string; character_references?: string[]; asset_references?: string[] }) =>
      client.production.createPlan(episodeId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: productionKeys.plan(episodeId) });
    },
  });
}

export function useShots(episodeId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: productionKeys.shots(episodeId),
    queryFn: () => client.production.listShots(episodeId),
    enabled: Boolean(episodeId),
  });
}

export function useCreateShot(episodeId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { scene_id?: string; shot_number?: number; camera_movement?: string; focal_length?: string; duration_seconds?: number }) =>
      client.production.createShot(episodeId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: productionKeys.shots(episodeId) });
      queryClient.invalidateQueries({ queryKey: productionKeys.plan(episodeId) });
    },
  });
}

export function useUpdateShot(episodeId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ shotId, ...data }: { shotId: string; camera_movement?: string; focal_length?: string; duration_seconds?: number; status?: string; audio_asset_id?: string; animation_asset_id?: string; render_asset_id?: string; expected_version: number }) =>
      client.production.updateShot(shotId, data),
    onSuccess: (updated: any) => {
      queryClient.invalidateQueries({ queryKey: productionKeys.shots(episodeId) });
      queryClient.invalidateQueries({ queryKey: productionKeys.shot(updated?.id) });
    },
  });
}

export function useProductionJobs(episodeId: string, stage?: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: productionKeys.jobs(episodeId, stage),
    queryFn: () => client.production.listJobs(episodeId, stage),
    enabled: Boolean(episodeId),
    refetchInterval: 3000,
  });
}

export function useProductionJob(jobId: string | undefined) {
  const client = useApiClient();
  return useQuery({
    queryKey: productionKeys.job(jobId ?? ''),
    queryFn: () => client.production.getJob(jobId!),
    enabled: Boolean(jobId),
  });
}

export function useSubmitStageJob(episodeId: string, stage: JobStage) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data?: { shot_id?: string; prompt_override?: string; correlation_id?: string }) => {
      switch (stage) {
        case 'AUDIO':
          return client.production.submitAudioJob(episodeId, data);
        case 'ANIMATION':
          return client.production.submitAnimationJob(episodeId, data);
        case 'RENDER':
          return client.production.submitRenderJob(episodeId, data);
        case 'VIDEO':
          return client.production.submitVideoJob(episodeId, data);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: productionKeys.jobs(episodeId) });
      queryClient.invalidateQueries({ queryKey: productionKeys.plan(episodeId) });
    },
  });
}

export function useCancelStageJob(episodeId: string, stage: JobStage) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, reason }: { jobId: string; reason?: string }) => {
      switch (stage) {
        case 'AUDIO':
          return client.production.cancelAudioJob(episodeId, jobId, reason);
        case 'ANIMATION':
          return client.production.cancelAnimationJob(episodeId, jobId, reason);
        case 'RENDER':
          return client.production.cancelRenderJob(episodeId, jobId, reason);
        case 'VIDEO':
          return client.production.cancelVideoJob(episodeId, jobId, reason);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: productionKeys.jobs(episodeId) });
    },
  });
}

export function useRetryStageJob(episodeId: string, stage: JobStage) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => {
      switch (stage) {
        case 'AUDIO':
          return client.production.retryAudioJob(episodeId, jobId);
        case 'ANIMATION':
          return client.production.retryAnimationJob(episodeId, jobId);
        case 'RENDER':
          return client.production.retryRenderJob(episodeId, jobId);
        case 'VIDEO':
          return client.production.retryVideoJob(episodeId, jobId);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: productionKeys.jobs(episodeId) });
    },
  });
}

export function useDeliveryArtifact(episodeId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: productionKeys.delivery(episodeId),
    queryFn: () => client.production.getDelivery(episodeId),
    enabled: Boolean(episodeId),
  });
}

/**
 * Production realtime hook via @windagent/realtime.
 * Streams progress and status updates for an episode production workflow.
 */
export function useProductionRealtime(episodeId: string, _apiBaseUrl?: string) {
  const queryClient = useQueryClient();
  const realtime = useRealtimeClient();

  useEffect(() => {
    if (!episodeId) return;

    const unsubscribe = realtime.subscribe(
      { aggregateType: 'production', aggregateId: episodeId },
      (evt) => {
        const eventType = evt.event_type || (evt.payload as any)?.event;
        if (
          eventType === 'production.snapshot' ||
          eventType?.startsWith('render.') ||
          eventType?.startsWith('audio.') ||
          eventType?.startsWith('animation.') ||
          eventType?.startsWith('video.')
        ) {
          queryClient.invalidateQueries({ queryKey: productionKeys.jobs(episodeId) });
          queryClient.invalidateQueries({ queryKey: productionKeys.shots(episodeId) });
          queryClient.invalidateQueries({ queryKey: productionKeys.plan(episodeId) });
        }
      }
    );

    return () => {
      unsubscribe();
    };
  }, [episodeId, realtime, queryClient]);
}
