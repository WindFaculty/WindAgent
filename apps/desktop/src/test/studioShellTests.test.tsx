/**
 * StudioPage shell tests (C3) — canonical StudioHomePage through real providers.
 * Server-backed data only: Series from /api/v3/studio/series and live health.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { StudioPage } from '@windagent/app';
import {
  jsonResponse,
  pathname,
  renderCanonical,
  series,
  type FetchFn,
} from './canonical';

let fetchMock: ReturnType<typeof vi.fn<FetchFn>>;

beforeEach(() => {
  window.location.hash = '#/studio';
  fetchMock = vi.fn<FetchFn>(async (input: string | URL) => {
    const path = pathname(input);
    if (path.endsWith('/api/v3/studio/series')) {
      return jsonResponse(200, { items: [series('proj_1', 'Chú thỏ và cánh diều')] });
    }
    if (path.endsWith('/api/v3/studio/series/proj_1/episodes')) {
      return jsonResponse(200, { items: [] });
    }
    if (path.endsWith('/health')) return jsonResponse(200, { status: 'healthy' });
    if (path.endsWith('/api/v3/project-templates')) return jsonResponse(200, []);
    throw new Error(`unmocked URL: ${path}`);
  });
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = '';
});

describe('StudioPage shell (C3) — canonical', () => {
  it('renders real projects from server with capability summary', async () => {
    renderCanonical(<StudioPage />);
    await waitFor(() => {
      expect(screen.getByText('Chú thỏ và cánh diều')).toBeInTheDocument();
    });
    expect(screen.getByText('STUDIO V3 CANONICAL')).toBeInTheDocument();
    expect(screen.getByText(/Trạng thái hệ thống: healthy/)).toBeInTheDocument();
  });

  it('shows degraded capability status when backend reports non-healthy', async () => {
    fetchMock.mockImplementation(async (input: string | URL) => {
      const path = pathname(input);
      if (path.endsWith('/api/v3/studio/series')) {
        return jsonResponse(200, { items: [] });
      }
      if (path.endsWith('/health')) return jsonResponse(200, { status: 'degraded' });
      if (path.endsWith('/api/v3/project-templates')) return jsonResponse(200, []);
      throw new Error(`unmocked URL: ${path}`);
    });
    renderCanonical(<StudioPage />);
    await waitFor(() => {
      expect(screen.getByText(/Trạng thái hệ thống: degraded/)).toBeInTheDocument();
    });
  });

  it('shows UNKNOWN status on network loss instead of fake values', async () => {
    fetchMock.mockImplementation(async (input: string | URL) => {
      const path = pathname(input);
      if (path.endsWith('/health')) throw new Error('network down');
      if (path.endsWith('/api/v3/project-templates')) return jsonResponse(200, []);
      return jsonResponse(200, { items: [] });
    });
    renderCanonical(<StudioPage />);
    await waitFor(() => {
      expect(screen.getByText(/Trạng thái hệ thống: UNKNOWN/)).toBeInTheDocument();
    });
  });

  it('never renders sample identifiers or fake data', async () => {
    renderCanonical(<StudioPage />);
    await waitFor(() => {
      expect(screen.getByText('Chú thỏ và cánh diều')).toBeInTheDocument();
    });
    expect(screen.queryByText(/srs_1/)).not.toBeInTheDocument();
    expect(screen.queryByText(/proj-alpha/)).not.toBeInTheDocument();
    expect(screen.queryByText(/episode_count/)).not.toBeInTheDocument();
  });

  it('navigates to the full Series catalog', async () => {
    renderCanonical(<StudioPage />);
    await waitFor(() => {
      expect(screen.getByText('Chú thỏ và cánh diều')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Xem tất cả'));
    await waitFor(() => {
      expect(window.location.hash).toBe('#/projects');
    });
  });
});
