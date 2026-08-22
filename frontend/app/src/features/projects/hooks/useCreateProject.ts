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

/**
 * P0.8 canonical-only: project (series) creation goes through the Studio
 * command API. No legacy fallback — a failed studio create is a failed mutation.
 */
export function useCreateProject() {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const mutation = useMutation<ProjectResource, CreateProjectInput, Error>({
    mutationFn: async (input: CreateProjectInput) => {
      const idempotencyKey = crypto.randomUUID();
      const res = await client.studio.createSeries(
        {
          title: input.name,
          description: input.description || '',
          metadata: {
            genre: input.genre || 'Sci-Fi',
            ...(input.initial_episode_title
              ? { initial_episode_title: input.initial_episode_title }
              : {}),
          },
        },
        idempotencyKey,
      );
      return {
        id: res.series_id,
        name: res.title,
        description: input.description || '',
        episodes_count: 0,
        metadata: { genre: input.genre },
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      } as unknown as ProjectResource;
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
