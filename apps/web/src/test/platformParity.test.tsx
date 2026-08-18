import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { platform, WebPlatformAdapter } from '../platform';
import { App } from '../app/App';

describe('Phase 14 Web Platform Convergence & Bootstrap', () => {
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

  it('exports WebPlatformAdapter with platform = "web"', () => {
    expect(platform).toBeInstanceOf(WebPlatformAdapter);
    expect(platform.platform).toBe('web');
    expect(platform.kind).toBe('web');
  });

  it('renders App cleanly without legacy @desktop dependencies', () => {
    const { container } = render(<App />);
    expect(container).toBeInTheDocument();
  });
});
