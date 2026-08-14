import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HttpStudioApiClient } from '@windagent/studio-client';
import { StudioStore } from '../StudioStore';

type FetchMock = ReturnType<typeof vi.fn>;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function series(id: string, title: string) {
  return { id, title, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', episode_count: 0 };
}

function episode(id: string, seriesId: string, state = 'DRAFT') {
  return { id, series_id: seriesId, title: `Ep ${id}`, state, version: 1 };
}

function run(id: string, status: string) {
  return {
    run_id: id,
    status,
    episode_id: 'ep_1',
    command_type: 'START_STORY_RUN',
    started_at: '2026-01-01T00:00:00Z',
  };
}

let fetchMock: FetchMock;

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock = vi.fn(async (input: string | URL) => {
    const url = String(input);
    if (url.endsWith('/api/v3/studio/series')) return jsonResponse(200, { items: [series('srs_1', 'T')] });
    if (url.includes('/series/srs_1/episodes')) return jsonResponse(200, { items: [episode('ep_1', 'srs_1')] });
    if (url.includes('/episodes/ep_1/artifacts')) {
      return jsonResponse(200, {
        items: [
          { artifact_id: 'art_1', artifact_type: 'IdeaCandidateSet', schema_version: 'studio.artifact/v1alpha1', series_id: 'srs_1', episode_id: 'ep_1' },
        ],
      });
    }
    if (url.endsWith('/api/v3/studio/runs/run_1/events?after=2')) {
      return jsonResponse(200, { events: [{ sequence: 3, event_type: 'studio.run.completed' }], next_after: 3 });
    }
    if (url.endsWith('/api/v3/studio/runs/run_1/events?after=0')) {
      return jsonResponse(200, { events: [{ sequence: 1, event_type: 'studio.run.started' }, { sequence: 2, event_type: 'studio.run.node_completed' }], next_after: 2 });
    }
    if (url.includes('/api/v3/studio/runs/run_1')) return jsonResponse(200, run('run_1', 'RUNNING'));
    if (url.includes('/api/v3/studio/runs/run_done')) return jsonResponse(200, run('run_done', 'COMPLETED'));
    if (url.includes('/api/v3/studio/episodes/ep_1')) return jsonResponse(200, episode('ep_1', 'srs_1'));
    if (url.includes('/api/v3/studio/series/srs_1')) return jsonResponse(200, series('srs_1', 'T'));
    if (url.includes('/api/v3/studio/capabilities')) {
      return jsonResponse(200, {
        capabilities: [{ name: 'studio_orchestration', status: 'AVAILABLE', reason: 'seam wired' }],
        fail_closed_flags: [],
        certification_mode: false,
      });
    }
    throw new Error(`unmocked URL: ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function makeStore(): StudioStore {
  const client = new HttpStudioApiClient({ baseUrl: 'http://studio.test', fetchImpl: fetchMock as unknown as typeof fetch });
  return new StudioStore(client);
}

describe('StudioStore caching and invalidation', () => {
  it('loads and caches series list', async () => {
    const store = makeStore();
    await store.loadSeriesList();
    expect(store.getSeriesList().map((s) => s.id)).toEqual(['srs_1']);
    await store.loadSeriesList();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('createSeries marks pending and invalidates the list', async () => {
    const store = makeStore();
    let resolvePost: (r: Response) => void = () => {};
    fetchMock.mockImplementation(async (input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === 'POST') {
        return new Promise<Response>((resolve) => {
          resolvePost = (r) => resolve(r);
        });
      }
      return jsonResponse(200, { items: [series('srs_1', 'T')] });
    });
    const promise = store.createSeries('key_1', 'T2');
    expect(store.isPending('key_1')).toBe(true);
    resolvePost(jsonResponse(201, { series_id: 'srs_2', title: 'T2', series_url: '/srs_2' }));
    await promise;
    expect(store.isPending('key_1')).toBe(false);
    expect(store.getLastError()).toBeNull();
  });
});

describe('StudioStore conflicts', () => {
  it('stale approval sets conflict and refetches server truth', async () => {
    const store = makeStore();
    fetchMock.mockImplementation(async (input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === 'POST') {
        return jsonResponse(409, {
          type: 'about:blank', title: 'Stale', status: 409, detail: 'stale rev_1; server at rev_2',
          code: 'STALE_REVISION', details: { episode_id: 'ep_1', current_revision_id: 'rev_2' },
        });
      }
      if (url.includes('/episodes/ep_1')) return jsonResponse(200, episode('ep_1', 'srs_1', 'IDEA_SELECTED'));
      return jsonResponse(200, { items: [] });
    });
    await store.recordApproval('k1', 'ep_1', {
      episode_id: 'ep_1', revision_id: 'rev_1', checkpoint: 'IDEA_SELECTION',
      artifact_hash: 'a'.repeat(64), decision: 'APPROVED', expected_optimistic_version: 1,
    });
    expect(store.getLastError()?.kind).toBe('conflict');
    expect(store.getConflict()?.episode_id).toBe('ep_1');
    expect(store.getConflict()?.code).toBe('STALE_REVISION');
    await vi.waitFor(() => expect(store.getEpisode('ep_1')?.state).toBe('IDEA_SELECTED'));
  });

  it('503 capability maps to capability_unavailable', async () => {
    const store = makeStore();
    fetchMock.mockImplementation(async () =>
      jsonResponse(503, {
        type: 'about:blank', title: 'Unavailable', status: 503, detail: 'orchestrator down',
        code: 'CAPABILITY_UNAVAILABLE', retryable: true,
      })
    );
    await store.loadRun('run_1');
    expect(store.getLastError()?.kind).toBe('capability_unavailable');
  });

  it('network failure maps to network error', async () => {
    const store = makeStore();
    fetchMock.mockImplementation(async () => {
      throw new TypeError('network down');
    });
    await store.loadRun('run_1');
    expect(store.getLastError()?.kind).toBe('network');
  });

  it('clears a recovered network error after the next successful request', async () => {
    const store = makeStore();
    let online = false;
    fetchMock.mockImplementation(async () => {
      if (!online) throw new TypeError('network down');
      return jsonResponse(200, { items: [series('srs_1', 'Recovered')] });
    });

    await store.loadSeriesList();
    expect(store.getLastError()?.kind).toBe('network');

    online = true;
    await store.loadSeriesList();
    expect(store.getLastError()).toBeNull();
    expect(store.getSeriesList()[0]?.title).toBe('Recovered');
  });

  it('maps an unstructured HTTP error separately from an offline error', async () => {
    const store = makeStore();
    fetchMock.mockImplementation(async () => jsonResponse(404, { detail: 'Not Found' }));

    await store.loadSeriesList();

    expect(store.getLastError()).toMatchObject({
      kind: 'http',
      status: 404,
      message: 'Studio API returned HTTP 404',
    });
  });

  it('capabilities surface orchestration status', async () => {
    const store = makeStore();
    await store.loadCapabilities();
    expect(store.getCapabilityStatus('studio_orchestration')).toBe('AVAILABLE');
  });
});

describe('StudioStore run polling and event cursor', () => {
  it('advances cursor, dedupes, stops on terminal status', async () => {
    const store = makeStore();
    let runCalls = 0;
    fetchMock.mockImplementation(async (input: string | URL) => {
      const url = String(input);
      if (url.includes('/runs/run_1/events')) {
        if (url.endsWith('after=0')) {
          return jsonResponse(200, { events: [{ sequence: 1, event_type: 'a' }, { sequence: 2, event_type: 'b' }], next_after: 2 });
        }
        return jsonResponse(200, { events: [{ sequence: 3, event_type: 'c' }], next_after: 3 });
      }
      if (url.includes('/runs/run_1')) {
        runCalls += 1;
        return jsonResponse(200, run('run_1', runCalls === 1 ? 'RUNNING' : 'COMPLETED'));
      }
      return jsonResponse(200, { items: [] });
    });
    const events: string[] = [];
    const stop = store.pollRun('run_1', { intervalMs: 1000, onEvent: (ev) => events.push(...ev.map((e) => e.event_type)) });
    await vi.advanceTimersByTimeAsync(1000);
    stop();
    expect(store.getEventCursor('run_1')).toBe(3);
    expect(events).toEqual(['a', 'b', 'c']);
  });

  it('hydrate restores cursor so polling resumes after last seen event', async () => {
    const store = makeStore();
    store.hydrate({ eventCursors: { run_1: 2 } });
    fetchMock.mockImplementation(async (input: string | URL) => {
      const url = String(input);
      if (url.endsWith('/runs/run_1/events?after=2')) {
        return jsonResponse(200, { events: [{ sequence: 3, event_type: 'resumed' }], next_after: 3 });
      }
      if (url.includes('/runs/run_1')) return jsonResponse(200, run('run_1', 'RUNNING'));
      return jsonResponse(200, { items: [] });
    });
    const events: string[] = [];
    const stop = store.pollRun('run_1', { intervalMs: 1000, onEvent: (ev) => events.push(...ev.map((e) => e.event_type)) });
    await vi.advanceTimersByTimeAsync(1000);
    stop();
    expect(events).toEqual(['resumed']);
    expect(store.serialize().eventCursors['run_1']).toBe(3);
  });
});

describe('StudioStore unsupported schema', () => {
  it('flags unknown artifact schema as unsupported', async () => {
    const store = makeStore();
    fetchMock.mockImplementation(async () =>
      jsonResponse(200, {
        items: [{ artifact_id: 'art_x', artifact_type: 'MysteryThing', schema_version: 'studio.artifact/v2', series_id: 'srs_1', episode_id: 'ep_1' }],
      })
    );
    await store.loadArtifacts('ep_1');
    const artifacts = store.getArtifacts('ep_1');
    expect(artifacts).toHaveLength(1);
    expect(store.isUnsupportedSchema(artifacts[0])).toBe(true);
  });
});
