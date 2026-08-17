import { useQuery } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';


export const CAPABILITIES_QUERY_KEY = ['v3', 'studio', 'capabilities'];

export interface CapabilitySnapshot {
  story_engine?: boolean;
  studio_orchestration?: boolean;
  worker?: boolean;
  [key: string]: boolean | undefined;
}

export function useCapabilities() {
  const client = useApiClient();

  const query = useQuery<{ status: string; capabilities: Record<string, string> }, Error>({
    queryKey: CAPABILITIES_QUERY_KEY,
    queryFn: async () => {
      // Direct typed get from readiness endpoint
      return client.system.getHealth() as any;
    },
    staleTimeMs: 30000,
  });


  const isReady = query.data?.status === 'healthy' || query.data?.status === 'ok' || query.data?.status === 'READY';

  return {
    isReady,
    status: query.data?.status ?? 'UNKNOWN',
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
  };
}
