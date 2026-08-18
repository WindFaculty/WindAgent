import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { platform, TauriPlatformAdapter } from '../platform';
import { App } from '../App';

describe('Phase 14 Desktop Platform Convergence & Bootstrap', () => {
  beforeEach(() => {
    window.location.hash = '#/dashboard';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (url: string) => {
        if (url.includes('/health')) {
          return new Response(JSON.stringify({ status: 'healthy' }), { status: 200 });
        }
        return new Response(JSON.stringify({}), { status: 200 });
      })
    );
  });

  it('exports TauriPlatformAdapter with platform = "desktop"', () => {
    expect(platform).toBeInstanceOf(TauriPlatformAdapter);
    expect(platform.platform).toBe('desktop');
    expect(platform.kind).toBe('tauri');
  });

  it('renders Desktop App cleanly through shared foundation', () => {
    const { container } = render(<App />);
    expect(container).toBeInTheDocument();
  });
});
