/**
 * Phase 13E — Settings Hooks.
 * Server-owned settings schema; frontend renders, never hardcodes semantics.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import type { SettingsResponse, SettingSchemaItem } from '@windagent/api-contracts';

export const settingsKeys = {
  all: ['v3', 'settings'] as const,
  schema: () => [...settingsKeys.all, 'schema'] as const,
  secrets: () => [...settingsKeys.all, 'secrets'] as const,
};

export function useSettings() {
  const client = useApiClient();
  return useQuery<SettingsResponse>({
    queryKey: settingsKeys.schema(),
    queryFn: () => client.settings.getSchema(),
  });
}

export function usePatchSettings() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, unknown>) => client.settings.patch(values),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: settingsKeys.schema() });
    },
  });
}

export function isSecretConfigured(item: SettingSchemaItem): boolean {
  const value = item.value as { configured?: boolean } | null | undefined;
  return Boolean(value && value.configured);
}

export function groupSettings(settings: SettingSchemaItem[]): Record<string, SettingSchemaItem[]> {
  const groups: Record<string, SettingSchemaItem[]> = {};
  for (const item of settings) {
    const g = item.group || 'general';
    (groups[g] ??= []).push(item);
  }
  return groups;
}