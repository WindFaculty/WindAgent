/**
 * Phase 9E — Assets Feature Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '@windagent/app/src/shared/hooks/useApiClient';

export const assetKeys = {
  all: ['assets-v3'] as const,
  list: (params?: object) => [...assetKeys.all, 'list', params] as const,
  detail: (assetId: string) => [...assetKeys.all, 'detail', assetId] as const,
  revisions: (assetId: string) => [...assetKeys.all, 'revisions', assetId] as const,
  provenance: (assetId: string) => [...assetKeys.all, 'provenance', assetId] as const,
  dependencies: (assetId: string) => [...assetKeys.all, 'dependencies', assetId] as const,
};

export function useAssets(params?: { episode_id?: string; project_id?: string; scene_id?: string; type?: string; status?: string }) {
  const client = useApiClient();
  return useQuery({
    queryKey: assetKeys.list(params),
    queryFn: () => client.assets.list(params),
  });
}

export function useCreateAsset() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      type?: string;
      episode_id?: string;
      project_id?: string;
      scene_id?: string;
      character_id?: string;
      source?: string;
      generator?: string;
      model?: string;
      prompt?: string;
      job_id?: string;
      parent_revision_id?: string;
      media_url?: string;
      content_base64?: string;
    }) => client.assets.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: assetKeys.all });
    },
  });
}

export function useAsset(assetId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: assetKeys.detail(assetId),
    queryFn: () => client.assets.get(assetId),
    enabled: Boolean(assetId),
  });
}

export function useAssetRevisions(assetId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: assetKeys.revisions(assetId),
    queryFn: () => client.assets.listRevisions(assetId),
    enabled: Boolean(assetId),
  });
}

export function useAssetProvenance(assetId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: assetKeys.provenance(assetId),
    queryFn: () => client.assets.getProvenance(assetId),
    enabled: Boolean(assetId),
  });
}

export function useAssetDependencies(assetId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: assetKeys.dependencies(assetId),
    queryFn: () => client.assets.getDependencies(assetId),
    enabled: Boolean(assetId),
  });
}

export function useApproveAsset(assetId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { revision_id: string; reason?: string; approved_by: string }) =>
      client.assets.approve(assetId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: assetKeys.detail(assetId) });
      queryClient.invalidateQueries({ queryKey: assetKeys.revisions(assetId) });
    },
  });
}

export function useRejectAsset(assetId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { revision_id: string; reason?: string; rejected_by: string }) =>
      client.assets.reject(assetId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: assetKeys.detail(assetId) });
      queryClient.invalidateQueries({ queryKey: assetKeys.revisions(assetId) });
    },
  });
}
