/**
 * Phase 12 — Providers Feature Hooks.
 */
import { useQuery, useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import { modelKeys } from '../../models/hooks/useModels';
import type {
  ProviderResource,
  ProviderEndpointResource,
  ProviderHealthMap,
  AddProviderRequest,
  AssignProviderModelRuleRequest,
  ProviderModelRuleResource,
  UpdateProviderRequest,
  RotateCredentialRequest,
  CredentialStatusResource,
  TestModelRequest,
  ModelDefinitionResource,
  StoryRoleResource,
} from '@windagent/api-contracts';

export const providerKeys = {
  all: ['providers'] as const,
  list: () => [...providerKeys.all, 'list'] as const,
  detail: (id: string) => [...providerKeys.all, 'detail', id] as const,
  endpoints: (id: string) => [...providerKeys.all, 'endpoints', id] as const,
  health: () => [...providerKeys.all, 'health'] as const,
  rules: () => [...providerKeys.all, 'rules'] as const,
  models: (id: string) => [...providerKeys.all, 'models', id] as const,
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

/** P0.3.3 — discovered models of one provider for the rule model selector. */
export function useProviderModels(providerId: string) {
  const client = useApiClient();
  return useQuery<ModelDefinitionResource[]>({
    queryKey: providerKeys.models(providerId),
    queryFn: () => client.providers.getModels(providerId),
    enabled: Boolean(providerId),
  });
}

/** P0.3.1 — canonical story routing roles (server authority). */
export function useStoryRoles() {
  const client = useApiClient();
  return useQuery<StoryRoleResource[]>({
    queryKey: ['routing', 'story-roles'],
    queryFn: () => client.routing.listStoryRoles(),
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

/** P0.1 — edit provider identity/endpoint/enabled state. */
export function useUpdateProvider() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { providerId: string; request: UpdateProviderRequest }) =>
      client.providers.update(args.providerId, args.request),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: providerKeys.list() });
      queryClient.invalidateQueries({ queryKey: providerKeys.detail(variables.providerId) });
      queryClient.invalidateQueries({ queryKey: providerKeys.health() });
    },
  });
}

/** P0.1 — delete provider; fails closed while routing rules depend on it. */
export function useDeleteProvider() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { providerId: string; allowDisablingRules?: boolean }) =>
      client.providers.remove(args.providerId, args.allowDisablingRules),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: providerKeys.list() });
      queryClient.invalidateQueries({ queryKey: providerKeys.health() });
      queryClient.invalidateQueries({ queryKey: providerKeys.rules() });
    },
  });
}

/** P0.1 — rotate or first-configure the API credential. */
export function useRotateProviderCredential() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { providerId: string; request: RotateCredentialRequest }) =>
      client.providers.rotateCredential(args.providerId, args.request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: providerKeys.list() });
    },
  });
}

/** P0.1 — remove the credential; endpoints become unconfigured. */
export function useRemoveProviderCredential(): UseMutationResult<CredentialStatusResource, Error, string> {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (providerId: string) => client.providers.removeCredential(providerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: providerKeys.list() });
    },
  });
}

/** P0.2.1 — explicit model catalog sync for one provider. */
export function useSyncProviderModels() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { providerId: string; endpointId?: string }) =>
      client.providers.syncModels(args.providerId, args.endpointId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: providerKeys.detail(variables.providerId) });
      queryClient.invalidateQueries({ queryKey: modelKeys.all });
    },
  });
}

/** P0.2.5 — verify one bound model with a tiny real inference. */
export function useTestProviderModel() {
  const client = useApiClient();
  return useMutation({
    mutationFn: (args: { providerId: string; request: TestModelRequest }) =>
      client.providers.testModel(args.providerId, args.request),
  });
}
