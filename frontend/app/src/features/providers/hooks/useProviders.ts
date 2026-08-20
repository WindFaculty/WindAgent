/**
 * Phase 12 — Providers Feature Hooks.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import type {
  ProviderResource,
  ProviderEndpointResource,
  ProviderHealthMap,
  AddProviderRequest,
  AssignProviderModelRuleRequest,
  ProviderModelRuleResource,
} from '@windagent/api-contracts';

export const providerKeys = {
  all: ['providers'] as const,
  list: () => [...providerKeys.all, 'list'] as const,
  detail: (id: string) => [...providerKeys.all, 'detail', id] as const,
  endpoints: (id: string) => [...providerKeys.all, 'endpoints', id] as const,
  health: () => [...providerKeys.all, 'health'] as const,
  rules: () => [...providerKeys.all, 'rules'] as const,
};

export function useProviders() {
  const client = useApiClient();
  return useQuery<ProviderResource[]>({
    queryKey: providerKeys.list(),
    queryFn: () => client.providers.list(),
  });
}

export function useCreateProvider() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: AddProviderRequest) => client.providers.create(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: providerKeys.list() });
      queryClient.invalidateQueries({ queryKey: providerKeys.health() });
    },
  });
}

export function useProvider(providerId: string) {
  const client = useApiClient();
  return useQuery<ProviderResource>({
    queryKey: providerKeys.detail(providerId),
    queryFn: () => client.providers.get(providerId),
    enabled: Boolean(providerId),
  });
}

export function useProviderEndpoints(providerId: string) {
  const client = useApiClient();
  return useQuery<ProviderEndpointResource[]>({
    queryKey: providerKeys.endpoints(providerId),
    queryFn: () => client.providers.getEndpoints(providerId),
    enabled: Boolean(providerId),
  });
}

export function useProvidersHealth() {
  const client = useApiClient();
  return useQuery<ProviderHealthMap>({
    queryKey: providerKeys.health(),
    queryFn: () => client.providers.getHealth(),
  });
}

export function useTestProviderConnection() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { providerId: string; endpointId?: string }) =>
      client.providers.testConnection(args.providerId, args.endpointId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: providerKeys.detail(variables.providerId) });
      queryClient.invalidateQueries({ queryKey: providerKeys.health() });
    },
  });
}

export function useProviderModelRules() {
  const client = useApiClient();
  return useQuery<ProviderModelRuleResource[]>({
    queryKey: providerKeys.rules(),
    queryFn: () => client.providers.listModelRules(),
  });
}

export function useAssignProviderModelRule() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: AssignProviderModelRuleRequest) =>
      client.providers.assignModelRule(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: providerKeys.rules() });
    },
  });
}
