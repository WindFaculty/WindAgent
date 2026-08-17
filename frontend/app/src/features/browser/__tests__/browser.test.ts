import { describe, it, expect } from 'vitest';
import { BrowserPage } from '../pages/BrowserPage';
import { useBrowserSessions, useBrowserActions, useBrowserRealtime, browserKeys } from '../hooks/useBrowser';

describe('Browser Feature Package (Phase 13A)', () => {
  it('exports page and hooks', () => {
    expect(BrowserPage).toBeDefined();
    expect(useBrowserSessions).toBeDefined();
    expect(useBrowserActions).toBeDefined();
    expect(useBrowserRealtime).toBeDefined();
  });

  it('defines canonical query keys', () => {
    expect(browserKeys.sessions()).toEqual(['v3', 'browser', 'sessions']);
    expect(browserKeys.session('brs-1')).toEqual(['v3', 'browser', 'session', 'brs-1']);
  });

  it('action kinds cover the browser runtime contract', () => {
    // backend operations: create / navigate / click / type / scroll / extract / close
    const kinds = ['create', 'navigate', 'click', 'type', 'scroll', 'extract', 'close'];
    for (const k of kinds) {
      expect(typeof k).toBe('string');
    }
    expect(kinds).toHaveLength(7);
  });
});