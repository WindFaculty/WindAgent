/**
 * useMonitoring Hook (Phase 6).
 * Manages queries for operational workers, providers, agents, queues, and runs.
 */

import { useCallback } from 'react';
import type {
  WorkersMonitoringResponse,
  ProvidersMonitoringResponse,
  AgentsMonitoringResponse,
  QueuesMonitoringResponse,
  RunsMonitoringResponse,
} from '@windagent/api-contracts';
import { useApiClient } from '../../../api/ApiProvider';
import { useQuery, useQueryClient } from '../../../query/QueryProvider';

export const MONITORING_QUERY_KEYS = {
  workers: ['v3', 'monitoring', 'workers'] as const,
  providers: ['v3', 'monitoring', 'providers'] as const,
  agents: ['v3', 'monitoring', 'agents'] as const,
  queues: ['v3', 'monitoring', 'queues'] as const,
  runs: ['v3', 'monitoring', 'runs'] as const,
};

export function useMonitoring() {
  const apiClient = useApiClient();
  const queryClient = useQueryClient();

  const workersQuery = useQuery<WorkersMonitoringResponse>({
    queryKey: MONITORING_QUERY_KEYS.workers,
    queryFn: () => apiClient.monitoring.getWorkers(),
    staleTimeMs: 5000,
  });

  const providersQuery = useQuery<ProvidersMonitoringResponse>({
    queryKey: MONITORING_QUERY_KEYS.providers,
    queryFn: () => apiClient.monitoring.getProviders(),
    staleTimeMs: 5000,
  });

  const agentsQuery = useQuery<AgentsMonitoringResponse>({
    queryKey: MONITORING_QUERY_KEYS.agents,
    queryFn: () => apiClient.monitoring.getAgents(),
    staleTimeMs: 5000,
  });

  const queuesQuery = useQuery<QueuesMonitoringResponse>({
    queryKey: MONITORING_QUERY_KEYS.queues,
    queryFn: () => apiClient.monitoring.getQueues(),
    staleTimeMs: 5000,
  });

  const runsQuery = useQuery<RunsMonitoringResponse>({
    queryKey: MONITORING_QUERY_KEYS.runs,
    queryFn: () => apiClient.monitoring.getRuns(),
    staleTimeMs: 5000,
  });

  const refetchAll = useCallback(async () => {
    queryClient.invalidateQueries({ queryKey: ['v3', 'monitoring'] });
    await Promise.all([
      workersQuery.refetch(),
      providersQuery.refetch(),
      agentsQuery.refetch(),
      queuesQuery.refetch(),
      runsQuery.refetch(),
    ]);
  }, [queryClient, workersQuery, providersQuery, agentsQuery, queuesQuery, runsQuery]);

  return {
    workers: workersQuery.data,
    providers: providersQuery.data,
    agents: agentsQuery.data,
    queues: queuesQuery.data,
    runs: runsQuery.data,
    isLoading:
      workersQuery.isLoading ||
      providersQuery.isLoading ||
      agentsQuery.isLoading ||
      queuesQuery.isLoading ||
      runsQuery.isLoading,
    refetchAll,
  };
}
