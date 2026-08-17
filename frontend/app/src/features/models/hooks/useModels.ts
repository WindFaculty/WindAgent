/**
 * Phase 12 — Models Feature Hooks.
 */
import { useQuery } from '@tanstack/react-query';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import type {
  ModelDefinitionResource,
  ModelFilterParams,
} from '@windagent/api-contracts';

export const modelKeys = {
  all: ['models'] as const,
  list: (params?: ModelFilterParams) => [...modelKeys.all, 'list', params ?? {}] as const,
  detail: (id: string) => [...modelKeys.all, 'detail', id] as const,
};

export function useModels(params?: ModelFilterParams) {
  const client = useApiClient();
  return useQuery<ModelDefinitionResource[]>({
    queryKey: modelKeys.list(params),
    queryFn: () => client.models.list(params),
  });
}

export function useModel(modelId: string) {
  const client = useApiClient();
  return useQuery<ModelDefinitionResource>({
    queryKey: modelKeys.detail(modelId),
    queryFn: () => client.models.get(modelId),
    enabled: Boolean(modelId),
  });
}
