/**
 * Phase 9A — Characters Feature Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '@windagent/app/src/shared/hooks/useApiClient';
import type { CharacterResource } from '@windagent/api-contracts';

export const characterKeys = {
  all: ['characters'] as const,
  list: (projectId: string) => [...characterKeys.all, 'list', projectId] as const,
  detail: (characterId: string) => [...characterKeys.all, 'detail', characterId] as const,
  relationships: (characterId: string) => [...characterKeys.all, 'relationships', characterId] as const,
};

export function useCharacters(projectId: string, search?: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: [...characterKeys.list(projectId), search],
    queryFn: () => client.characters.list(projectId, search),
    enabled: Boolean(projectId),
  });
}

export function useCharacter(characterId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: characterKeys.detail(characterId),
    queryFn: () => client.characters.get(characterId),
    enabled: Boolean(characterId),
  });
}

export function useCreateCharacter(projectId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; role?: string; biography?: string; dominant_trait?: string; flaw?: string; alignment_score?: number; voice_style?: string }) =>
      client.characters.create(projectId, data, `create-char-${Date.now()}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterKeys.list(projectId) });
    },
  });
}

export function useUpdateCharacter() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ characterId, ...data }: { characterId: string; name?: string; role?: string; biography?: string; dominant_trait?: string; flaw?: string; alignment_score?: number; expected_version: number }) =>
      client.characters.update(characterId, data),
    onSuccess: (updated: CharacterResource) => {
      queryClient.invalidateQueries({ queryKey: characterKeys.detail(updated.id) });
    },
  });
}

export function useDeleteCharacter(projectId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (characterId: string) => client.characters.delete(characterId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: characterKeys.list(projectId) });
    },
  });
}

export function useCharacterRelationships(characterId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: characterKeys.relationships(characterId),
    queryFn: () => client.characters.getRelationships(characterId),
    enabled: Boolean(characterId),
  });
}
