/**
 * Canonical page test helpers — providers + fetch mocks for @windagent/app pages.
 * Pages under test need ApiProvider (useApiClient), QueryClientProvider (TanStack),
 * and RouterProvider (hash-based navigation).
 */
import React from 'react';
import { render } from '@testing-library/react';
import { AppProviders } from '@windagent/app/src/app/providers';

export type FetchFn = (input: string | URL, init?: RequestInit) => Promise<Response>;

export function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export interface RenderCanonicalOptions {
  initialHash?: string;
  fetchMock?: FetchFn;
}

/** Render a canonical page with the real provider tree; global fetch is stubbed by the caller. */
export function renderCanonical(ui: React.ReactElement, options: RenderCanonicalOptions = {}) {
  if (options.initialHash) window.location.hash = options.initialHash;
  return render(<AppProviders>{ui}</AppProviders>);
}

/** Pathname matcher for mocked fetch — ignores baseUrl/host, matches suffix. */
export function pathname(url: string | URL): string {
  return new URL(String(url), 'http://localhost').pathname;
}

export function project(id: string, name: string, genre = 'Drama / Mystery Noir') {
  return {
    id,
    name,
    description: `Mo ta ${name}`,
    metadata: { genre },
    episodes_count: 0,
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

/** Canonical Studio Series resource returned by /api/v3/studio/series. */
export function series(id: string, title: string, genre = 'Drama / Mystery Noir') {
  return {
    id,
    title,
    description: `Mo ta ${title}`,
    metadata: { genre },
    episode_count: 0,
    episode_ids: [],
    optimistic_version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

export function cursorPage(items: unknown[]) {
  return { items, page_info: { next_cursor: null, has_more: false } };
}
