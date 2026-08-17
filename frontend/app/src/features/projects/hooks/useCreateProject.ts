import { useMutation, useQueryClient } from '../../../query';
import { useApiClient } from '../../../api/ApiProvider';

import { PROJECTS_QUERY_KEY } from './useProjects';
import type { ProjectResource } from '@windagent/api-contracts';

export interface CreateProjectInput {
  name: string;
  description?: string;
  genre?: string;
  initial_episode_title?: string;
}

export function useCreateProject() {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const mutation = useMutation<ProjectResource, CreateProjectInput, Error>({
    mutationFn: async (input: CreateProjectInput) => {
      // Auto-generate RFC-4122 v4 UUID idempotency key
      const idempotencyKey = crypto.randomUUID();
      return client.projects.create(input, idempotencyKey);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY });
    },
  });

  return {
    createProject: mutation.mutateAsync,
    isCreating: mutation.isLoading,
    isError: Boolean(mutation.error),
    error: mutation.error,
  };
}

