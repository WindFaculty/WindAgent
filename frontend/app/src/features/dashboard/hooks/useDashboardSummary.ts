/**
 * useDashboardSummary Hook (Phase 6).
 * Consumes canonical V3 /api/v3/dashboard/summary via QueryClient.
 */

import { useCallback } from 'react';
import type { DashboardSummary } from '@windagent/api-contracts';
import { useApiClient } from '../../../api/ApiProvider';
import { useQuery, useQueryClient } from '../../../query/QueryProvider';

export const DASHBOARD_SUMMARY_QUERY_KEY = ['v3', 'dashboard', 'summary'] as const;

export function useDashboardSummary() {
  const apiClient = useApiClient();
  const queryClient = useQueryClient();

  const query = useQuery<DashboardSummary>({
    queryKey: DASHBOARD_SUMMARY_QUERY_KEY,
    queryFn: () => apiClient.dashboard.getSummary(),
    staleTimeMs: 10000,
  });

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: DASHBOARD_SUMMARY_QUERY_KEY });
  }, [queryClient]);

  return {
    summary: query.data,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    invalidate,
  };
}
