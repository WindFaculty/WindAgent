/**
 * Phase 13C — Memory Hooks.
 * Memory != Database: scoped knowledge records with retrieval.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import type { CreateMemoryRequest, MemoryRecordResource, MemoryScope, MemoryType } from '@windagent/api-contracts';

export const memoryKeys = {
  all: ['v3', 'memory'] as const,
  list: (scope?: string) => [...memoryKeys.all, 'list', scope ?? 'all'] as const,
  search: (query: string) => [...memoryKeys.all, 'search', query] as const,
};

export const MEMORY_SCOPES: MemoryScope[] = ['conversation', 'project', 'agent', 'global'];
export const MEMORY_TYPES: MemoryType[] = ['working', 'short_term', 'long_term'];

export function useMemoryRecords(scope?: MemoryScope) {
  const client = useApiClient();
  return useQuery<MemoryRecordResource[]>({
    queryKey: memoryKeys.list(scope),
    queryFn: () => client.memory.list(scope ? { scope } : undefined),
  });
}

export function useCreateMemory() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateMemoryRequest) => client.memory.create(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: memoryKeys.all }),
  });
}

export function useMemorySearch(query: string) {
  const client = useApiClient();
  return useQuery<MemoryRecordResource[]>({
    queryKey: memoryKeys.search(query),
    queryFn: () => client.memory.search({ query }),
    enabled: Boolean(query.trim()),
  });
}