/**
 * Phase 12 — Routing Feature Hooks.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import type {
  RoutingRuleResource,
  RoutingGraphData,
  RoutingMetricsData,
  RouteSimulationRequest,
  RouteLockDetailResource,
} from '@windagent/api-contracts';

export const routingKeys = {
  all: ['routing'] as const,
  rules: () => [...routingKeys.all, 'rules'] as const,
  rule: (id: string) => [...routingKeys.all, 'rule', id] as const,
  graph: () => [...routingKeys.all, 'graph'] as const,
  metrics: () => [...routingKeys.all, 'metrics'] as const,
  lock: (id: string) => [...routingKeys.all, 'lock', id] as const,
};

export function useRoutingRules() {
  const client = useApiClient();
  return useQuery<RoutingRuleResource[]>({
    queryKey: routingKeys.rules(),
    queryFn: () => client.routing.listRules(),
  });
}

export function useRoutingRule(ruleId: string) {
  const client = useApiClient();
  return useQuery<RoutingRuleResource>({
    queryKey: routingKeys.rule(ruleId),
    queryFn: () => client.routing.getRule(ruleId),
    enabled: Boolean(ruleId),
  });
}

export function useCreateRoutingRule() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (rule: Partial<RoutingRuleResource>) => client.routing.createRule(rule),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: routingKeys.rules() });
      queryClient.invalidateQueries({ queryKey: routingKeys.graph() });
      queryClient.invalidateQueries({ queryKey: routingKeys.metrics() });
    },
  });
}

export function useUpdateRoutingRule() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { ruleId: string; updates: Partial<RoutingRuleResource> & { expected_version?: number } }) =>
      client.routing.updateRule(args.ruleId, args.updates),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: routingKeys.rule(variables.ruleId) });
      queryClient.invalidateQueries({ queryKey: routingKeys.rules() });
      queryClient.invalidateQueries({ queryKey: routingKeys.graph() });
      queryClient.invalidateQueries({ queryKey: routingKeys.metrics() });
    },
  });
}

export function useDeleteRoutingRule() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ruleId: string) => client.routing.deleteRule(ruleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: routingKeys.rules() });
      queryClient.invalidateQueries({ queryKey: routingKeys.graph() });
      queryClient.invalidateQueries({ queryKey: routingKeys.metrics() });
    },
  });
}

export function useRoutingGraph() {
  const client = useApiClient();
  return useQuery<RoutingGraphData>({
    queryKey: routingKeys.graph(),
    queryFn: () => client.routing.getGraph(),
  });
}

export function useRoutingMetrics() {
  const client = useApiClient();
  return useQuery<RoutingMetricsData>({
    queryKey: routingKeys.metrics(),
    queryFn: () => client.routing.getMetrics(),
  });
}

export function useSimulateRoute() {
  const client = useApiClient();
  return useMutation({
    mutationFn: (request: RouteSimulationRequest) => client.routing.simulate(request),
  });
}

export function useRouteLock(lockId: string) {
  const client = useApiClient();
  return useQuery<RouteLockDetailResource>({
    queryKey: routingKeys.lock(lockId),
    queryFn: () => client.routing.getLock(lockId),
    enabled: Boolean(lockId),
  });
}
