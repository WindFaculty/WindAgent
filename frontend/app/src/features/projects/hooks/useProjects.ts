import { useQuery, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';

import type { ProjectResource, CursorPage } from '@windagent/api-contracts';

export const PROJECTS_QUERY_KEY = ['v3', 'projects'];

export interface UseProjectsOptions {
  search?: string;
  genre?: string;
  cursor?: string;
  limit?: number;
}

export function useProjects(options?: UseProjectsOptions) {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const query = useQuery<CursorPage<ProjectResource>, Error>({
    queryKey: [...PROJECTS_QUERY_KEY, options?.search ?? '', options?.genre ?? 'all'],
    queryFn: async () => {
      return client.projects.list(options);
    },
    staleTimeMs: 10000,
  });


  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY });
  };

  return {
    projects: query.data?.items ?? [],
    pageInfo: query.data?.page_info,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    invalidate,
  };
}
