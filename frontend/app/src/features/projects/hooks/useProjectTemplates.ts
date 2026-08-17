import { useQuery } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';

import type { ProjectTemplate } from '@windagent/api-contracts';

export const PROJECT_TEMPLATES_QUERY_KEY = ['v3', 'project-templates'];

export function useProjectTemplates() {
  const client = useApiClient();

  const query = useQuery<ProjectTemplate[], Error>({
    queryKey: PROJECT_TEMPLATES_QUERY_KEY,
    queryFn: async () => {
      return client.projects.getTemplates();
    },
    staleTimeMs: 60000,
  });


  return {
    templates: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
  };
}
