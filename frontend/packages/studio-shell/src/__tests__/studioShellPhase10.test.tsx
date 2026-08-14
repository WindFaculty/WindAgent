import { describe, it, expect } from 'vitest';
import { DESKTOP_NAVIGATION_GROUPS } from '../index';

describe('Phase UI10 — Production Isolation & System Regroup', () => {
  it('isolates Production navigation group with ROADMAP 2 badge and defaultCollapsed flag', () => {
    const prodGroup = DESKTOP_NAVIGATION_GROUPS.find((g) => g.id === 'production');
    expect(prodGroup).toBeDefined();
    expect(prodGroup?.title).toBe('PRODUCTION');
    expect(prodGroup?.badge).toBe('ROADMAP 2');
    expect(prodGroup?.defaultCollapsed).toBe(true);

    const prodItem = prodGroup?.items.find((i) => i.id === 'production');
    expect(prodItem?.badge).toBe('PREVIEW');
    expect(prodItem?.children).toBeDefined();
    expect(prodItem?.children?.map((c) => c.id)).toEqual([
      'production-script',
      'production-assets',
      'production-video',
    ]);
  });

  it('regroups System navigation group with truthful stub and experimental badges', () => {
    const sysGroup = DESKTOP_NAVIGATION_GROUPS.find((g) => g.id === 'system');
    expect(sysGroup).toBeDefined();
    expect(sysGroup?.title).toBe('SYSTEM');

    const itemIds = sysGroup?.items.map((i) => i.id);
    expect(itemIds).toContain('workspace');
    expect(itemIds).toContain('router');
    expect(itemIds).toContain('browser');
    expect(itemIds).toContain('files');
    expect(itemIds).toContain('settings');

    const browserItem = sysGroup?.items.find((i) => i.id === 'browser');
    expect(browserItem?.badge).toBe('STUB');

    const filesItem = sysGroup?.items.find((i) => i.id === 'files');
    expect(filesItem?.badge).toBe('STUB');
  });
});
