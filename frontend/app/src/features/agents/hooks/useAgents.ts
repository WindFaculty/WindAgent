/**
 * Phase 11 — Agents Feature Hooks.
 * Provides query/mutation hooks for Agent Definitions, Instances,
 * Activity, and Truthful Summary Metrics (No 5s polling intervals).
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import type {
  AgentDefinitionResource,
  AgentInstanceResource,
  AgentSummaryMetrics,
  AgentActivityItem,
} from '@windagent/api-contracts';

export const agentKeys = {
  all: ['agents'] as const,
  definitions: (params?: { search?: string; role?: string }) => [...agentKeys.all, 'definitions', params ?? {}] as const,
  definition: (id: string) => [...agentKeys.all, 'definition', id] as const,
  activity: (id: string) => [...agentKeys.all, 'activity', id] as const,
  metrics: () => [...agentKeys.all, 'metrics'] as const,
  instances: (params?: { conversation_id?: string; status?: string }) => [...agentKeys.all, 'instances', params ?? {}] as const,
  instance: (id: string) => [...agentKeys.all, 'instance', id] as const,
};

export function useAgentDefinitions(params?: { search?: string; role?: string }) {
  const client = useApiClient();
  return useQuery<AgentDefinitionResource[]>({
    queryKey: agentKeys.definitions(params),
    queryFn: () => client.agentDefinitions.list(params),
  });
}

export function useAgentDefinition(definitionId: string) {
  const client = useApiClient();
  return useQuery<AgentDefinitionResource>({
    queryKey: agentKeys.definition(definitionId),
    queryFn: () => client.agentDefinitions.get(definitionId),
    enabled: Boolean(definitionId),
  });
}

export function useCreateAgentDefinition() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      slug?: string;
      description?: string;
      role: string;
      model_policy?: Record<string, unknown>;
      tool_policy?: Record<string, unknown>;
      permission_profile?: Record<string, unknown>;
      memory_policy?: Record<string, unknown>;
      default_configuration?: Record<string, unknown>;
    }) => client.agentDefinitions.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.all });
    },
  });
}

export function useUpdateAgentDefinition() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      definitionId: string;
      data: {
        name?: string;
        slug?: string;
        description?: string;
        role?: string;
        model_policy?: Record<string, unknown>;
        tool_policy?: Record<string, unknown>;
        permission_profile?: Record<string, unknown>;
        memory_policy?: Record<string, unknown>;
        default_configuration?: Record<string, unknown>;
        expected_version: number;
      };
    }) => client.agentDefinitions.update(args.definitionId, args.data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: agentKeys.definition(variables.definitionId) });
      queryClient.invalidateQueries({ queryKey: agentKeys.all });
    },
  });
}

export function useDeleteAgentDefinition() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (definitionId: string) => client.agentDefinitions.delete(definitionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.all });
    },
  });
}

export function useAgentActivity(definitionId: string) {
  const client = useApiClient();
  return useQuery<AgentActivityItem[]>({
    queryKey: agentKeys.activity(definitionId),
    queryFn: () => client.agentDefinitions.getActivity(definitionId),
    enabled: Boolean(definitionId),
  });
}

export function useAgentMetrics() {
  const client = useApiClient();
  return useQuery<AgentSummaryMetrics>({
    queryKey: agentKeys.metrics(),
    queryFn: () => client.agentDefinitions.getMetrics(),
  });
}

export function useAgentInstances(params?: { conversation_id?: string; status?: string }) {
  const client = useApiClient();
  return useQuery<AgentInstanceResource[]>({
    queryKey: agentKeys.instances(params),
    queryFn: () => client.agentInstances.list(params),
  });
}

export function useStartAgentInstance() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (instanceId: string) => client.agentInstances.start(instanceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.instances() });
      queryClient.invalidateQueries({ queryKey: agentKeys.metrics() });
    },
  });
}

export function useStopAgentInstance() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (instanceId: string) => client.agentInstances.stop(instanceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.instances() });
      queryClient.invalidateQueries({ queryKey: agentKeys.metrics() });
    },
  });
}

export function useRestartAgentInstance() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (instanceId: string) => client.agentInstances.restart(instanceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.instances() });
      queryClient.invalidateQueries({ queryKey: agentKeys.metrics() });
    },
  });
}
