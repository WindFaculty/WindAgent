/**
 * Phase 13B — Workspace Files Hooks.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import type { CreateFileRequest, FileResource } from '@windagent/api-contracts';

export const filesKeys = {
  all: ['v3', 'files'] as const,
  list: () => [...filesKeys.all, 'list'] as const,
};

export function useFiles() {
  const client = useApiClient();
  return useQuery<FileResource[]>({
    queryKey: filesKeys.list(),
    queryFn: () => client.files.list(),
  });
}

export function useCreateFile() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateFileRequest) => client.files.create(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: filesKeys.list() }),
  });
}

export function useDeleteFile() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (fileId: string) => client.files.remove(fileId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: filesKeys.list() }),
  });
}