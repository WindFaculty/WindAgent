import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StudioPage } from '../pages/StudioPage';

type FetchFn = (input: string | URL, init?: RequestInit) => Promise<Response>;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function series(id: string, title: string, episodeCount = 0) {
  return { id, title, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', episode_count: episodeCount };
}

function episode(id: string, seriesId: string, state = 'DRAFT') {
  return {
    id, series_id: seriesId, title: `Ep ${id}`, episode_number: 1,
    state, version: 1, optimistic_version: 1, current_revision_id: null, active_run_id: null,
    awaiting_checkpoint: null, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  };
}

const CAPABILITIES = {
  capabilities: [
    { name: 'durable_db', status: 'AVAILABLE', reason: 'db' },
    { name: 'studio_orchestration', status: 'AVAILABLE', reason: 'seam' },
    { name: 'story_engine', status: 'UNAVAILABLE', reason: 'A5' },
    { name: 'worker', status: 'UNAVAILABLE', reason: 'none' },
    { name: 'model_route', status: 'AVAILABLE', reason: 'route' },
  ],
  fail_closed_flags: [],
  certification_mode: false,
};

let fetchMock: ReturnType<typeof vi.fn<FetchFn>>;

beforeEach(() => {
  window.location.hash = '#/studio';
  fetchMock = vi.fn<FetchFn>(async (input: string | URL) => {
    const url = String(input);
    if (url.endsWith('/api/v3/studio/capabilities')) return jsonResponse(200, CAPABILITIES);
    if (url.endsWith('/api/v3/studio/series')) return jsonResponse(200, { items: [series('srs_1', 'Chú thỏ và cánh diều', 1)] });
    if (url.includes('/series/srs_1/episodes')) return jsonResponse(200, { items: [episode('ep_1', 'srs_1')] });
    if (url.includes('/episodes/ep_1/artifacts')) {
      return jsonResponse(200, {
        items: [{ artifact_id: 'art_1', artifact_type: 'IdeaCandidateSet', schema_version: 'studio.artifact/v1alpha1', series_id: 'srs_1', episode_id: 'ep_1' }],
      });
    }
    if (url.includes('/api/v3/studio/episodes/ep_1')) return jsonResponse(200, episode('ep_1', 'srs_1'));
    throw new Error(`unmocked URL: ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = '';
});

describe('StudioPage shell (C3)', () => {
  it('renders real series from server with capability summary', async () => {
    render(<StudioPage />);
    expect(await screen.findByText('Chú thỏ và cánh diều (1 episodes)')).toBeInTheDocument();
    expect(screen.getByText('durable_db: AVAILABLE')).toBeInTheDocument();
    expect(screen.getByText('story_engine: UNAVAILABLE')).toBeInTheDocument();
  });

  it('navigates to series detail and episode detail via hash links', async () => {
    render(<StudioPage />);
    const link = await screen.findByRole('link', { name: /Chú thỏ/ });
    fireEvent.click(link);
    expect(await screen.findByText('Episodes')).toBeInTheDocument();
    const epLink = await screen.findByRole('link', { name: /Ep ep_1/ });
    fireEvent.click(epLink);
    expect(await screen.findByText('Start / resume run')).toBeInTheDocument();
    expect(screen.getByText('IdeaCandidateSet')).toBeInTheDocument();
    expect(window.location.hash).toBe('#/studio/episodes/ep_1');
  });

  it('shows capability-unavailable fail-closed banner', async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse(503, {
        type: 'about:blank', title: 'Unavailable', status: 503, detail: 'orchestrator down',
        code: 'CAPABILITY_UNAVAILABLE', retryable: true,
      })
    );
    render(<StudioPage />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Capability unavailable'));
  });

  it('shows offline banner on network loss', async () => {
    fetchMock.mockImplementation(async () => {
      throw new TypeError('network down');
    });
    render(<StudioPage />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Offline'));
  });

  it('renders unsupported artifact schema as unsupported, not blank', async () => {
    fetchMock.mockImplementation(async (input: string | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v3/studio/capabilities')) return jsonResponse(200, CAPABILITIES);
      if (url.endsWith('/api/v3/studio/series')) return jsonResponse(200, { items: [series('srs_1', 'S', 1)] });
      if (url.includes('/series/srs_1/episodes')) return jsonResponse(200, { items: [episode('ep_1', 'srs_1')] });
      if (url.includes('/episodes/ep_1/artifacts')) {
        return jsonResponse(200, {
          items: [{ artifact_id: 'art_x', artifact_type: 'MysteryThing', schema_version: 'studio.artifact/v2', series_id: 'srs_1', episode_id: 'ep_1' }],
        });
      }
      if (url.includes('/api/v3/studio/episodes/ep_1')) return jsonResponse(200, episode('ep_1', 'srs_1'));
      throw new Error(`unmocked URL: ${url}`);
    });
    render(<StudioPage />);
    const link = await screen.findByRole('link', { name: /^S \(1/ });
    fireEvent.click(link);
    const epLink = await screen.findByRole('link', { name: /Ep ep_1/ });
    fireEvent.click(epLink);
    expect(await screen.findByText(/unsupported schema studio.artifact\/v2/)).toBeInTheDocument();
  });

  it('never renders sample identifiers or fake data', async () => {
    render(<StudioPage />);
    await screen.findByText('Chú thỏ và cánh diều (1 episodes)');
    expect(screen.queryByText(/proj-alpha/)).not.toBeInTheDocument();
    expect(screen.queryByText(/vp_001/)).not.toBeInTheDocument();
  });
});
