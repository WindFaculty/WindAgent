/**
 * Phase 9B — World Bible Feature Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '@windagent/app/src/shared/hooks/useApiClient';

export const worldKeys = {
  all: ['world'] as const,
  bible: (projectId: string) => [...worldKeys.all, 'bible', projectId] as const,
  locations: (projectId: string) => [...worldKeys.all, 'locations', projectId] as const,
  factions: (projectId: string) => [...worldKeys.all, 'factions', projectId] as const,
  lore: (projectId: string) => [...worldKeys.all, 'lore', projectId] as const,
};

export function useWorldBible(projectId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: worldKeys.bible(projectId),
    queryFn: () => client.world.getWorldBible(projectId),
    enabled: Boolean(projectId),
  });
}

export function useLocations(projectId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: worldKeys.locations(projectId),
    queryFn: () => client.world.listLocations(projectId),
    enabled: Boolean(projectId),
  });
}

export function useFactions(projectId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: worldKeys.factions(projectId),
    queryFn: () => client.world.listFactions(projectId),
    enabled: Boolean(projectId),
  });
}

export function useLore(projectId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: worldKeys.lore(projectId),
    queryFn: () => client.world.listLore(projectId),
    enabled: Boolean(projectId),
  });
}

export function useUpdateWorldBible(projectId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { world_name?: string; setting_summary?: string; core_theme?: string; rules?: string[]; timeline_era?: string; expected_version: number }) =>
      client.world.updateWorldBible(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: worldKeys.bible(projectId) });
    },
  });
}

export function useCreateLocation(projectId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; type?: string; description?: string; atmosphere?: string }) =>
      client.world.createLocation(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: worldKeys.locations(projectId) });
    },
  });
}

export function useCreateFaction(projectId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; ideology?: string; influence_level?: number; description?: string }) =>
      client.world.createFaction(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: worldKeys.factions(projectId) });
    },
  });
}

export function useCreateLore(projectId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { title: string; category?: string; content?: string }) =>
      client.world.createLore(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: worldKeys.lore(projectId) });
    },
  });
}
