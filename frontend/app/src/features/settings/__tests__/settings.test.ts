import { describe, it, expect } from 'vitest';
import { SettingsPage } from '../pages/SettingsPage';
import { useSettings, usePatchSettings, isSecretConfigured, groupSettings, settingsKeys } from '../hooks/useSettings';
import type { SettingSchemaItem } from '@windagent/api-contracts';

describe('Settings Feature Package (Phase 13E)', () => {
  it('exports page and hooks', () => {
    expect(SettingsPage).toBeDefined();
    expect(useSettings).toBeDefined();
    expect(usePatchSettings).toBeDefined();
  });

  it('defines canonical query keys', () => {
    expect(settingsKeys.schema()).toEqual(['v3', 'settings', 'schema']);
  });

  it('secret values render as configured-status only', () => {
    const secretItem: SettingSchemaItem = {
      key: 'integration.google_api_key',
      type: 'secret',
      group: 'integrations',
      value: { configured: true },
      secret: true,
    };
    const plainItem: SettingSchemaItem = {
      key: 'appearance.theme',
      type: 'enum',
      group: 'appearance',
      value: 'dark',
    };
    expect(isSecretConfigured(secretItem)).toBe(true);
    expect(isSecretConfigured(plainItem)).toBe(false);
  });

  it('groups settings by schema group', () => {
    const items: SettingSchemaItem[] = [
      { key: 'appearance.theme', type: 'enum', group: 'appearance' },
      { key: 'agent.max_concurrent_instances', type: 'number', group: 'agent' },
      { key: 'appearance.language', type: 'enum', group: 'appearance' },
    ];
    const groups = groupSettings(items);
    expect(Object.keys(groups).sort()).toEqual(['agent', 'appearance']);
    expect(groups.appearance).toHaveLength(2);
  });
});