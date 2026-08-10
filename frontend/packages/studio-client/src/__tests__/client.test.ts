import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  HttpStudioApiClient,
  StudioApiError,
  StudioNetworkError,
  StudioTimeoutError,
  isRetryableError,
} from '../HttpStudioApiClient';

type FetchFn = (input: string | URL, init?: RequestInit) => Promise<Response>;
type FetchMock = ReturnType<typeof vi.fn>;
type FetchCall = [string | URL, RequestInit?];

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function makeClient(fetchImpl: typeof fetch) {
  return new HttpStudioApiClient({ baseUrl: 'http://studio.test', fetchImpl });
}

describe('HttpStudioApiClient reads', () => {
  it('lists series through GET /api/v3/studio/series', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [{ id: 'srs_1', title: 'T' }] })
    );
    const client = makeClient(fetchMock as unknown as typeof fetch);
    const res = await client.listSeries();
    expect(res.items).toHaveLength(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as FetchCall;
    expect(url).toBe('http://studio.test/api/v3/studio/series');
    expect(init?.method).toBe('GET');
  });

  it('fetches run events with the exclusive cursor', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { events: [{ sequence: 4, event_type: 'studio.run.node_completed' }], next_after: 4 })
    );
    const client = makeClient(fetchMock as unknown as typeof fetch);
    const res = await client.getRunEvents('run_1', 3);
    expect(res.events[0].sequence).toBe(4);
    const url: string = String((fetchMock.mock.calls[0] as unknown as FetchCall)[0]);
    expect(url).toContain('/runs/run_1/events?after=3');
  });

  it('retries a GET once on network failure', async () => {
    let calls = 0;
    const fetchMock = vi.fn(async () => {
      calls += 1;
      if (calls === 1) throw new TypeError('network down');
      return jsonResponse(200, { items: [] });
    });
    const client = makeClient(fetchMock as unknown as typeof fetch);
    await expect(client.listSeries()).resolves.toEqual({ items: [] });
    expect(calls).toBe(2);
  });

  it('surfaces network loss as retryable StudioNetworkError after the retry', async () => {
    const fetchMock = vi.fn(async () => {
      throw new TypeError('network down');
    });
    const client = makeClient(fetchMock as unknown as typeof fetch);
    await expect(client.listSeries()).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(StudioNetworkError);
      expect(isRetryableError(err)).toBe(true);
      return true;
    });
  });

  it('aborts with StudioTimeoutError when the request hangs', async () => {
    const fetchMock = vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError'))
          );
        })
    );
    const client = new HttpStudioApiClient({
      baseUrl: 'http://studio.test',
      fetchImpl: fetchMock as unknown as typeof fetch,
      timeoutMs: 20,
    });
    await expect(client.listSeries()).rejects.toBeInstanceOf(StudioTimeoutError);
  });
});

describe('HttpStudioApiClient mutations', () => {
  it('sends X-Idempotency-Key on every mutation', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(201, { series_id: 'srs_1', title: 'T', series_url: '/srs_1' })
    );
    const client = makeClient(fetchMock as unknown as typeof fetch);
    await client.createSeries('idem_abc', { title: 'T' });
    const [, init] = fetchMock.mock.calls[0] as unknown as FetchCall;
    const headers = init?.headers as Record<string, string> | undefined;
    expect(headers?.['X-Idempotency-Key']).toBe('idem_abc');
  });

  it('does NOT retry a failed mutation (caller replays with same key)', async () => {
    let calls = 0;
    const fetchMock = vi.fn(async () => {
      calls += 1;
      return jsonResponse(503, {
        type: 'about:blank',
        title: 'Capability unavailable',
        status: 503,
        detail: 'orchestrator missing',
        code: 'CAPABILITY_UNAVAILABLE',
        retryable: true,
      });
    });
    const client = makeClient(fetchMock as unknown as typeof fetch);
    await expect(client.startRun('idem_1', 'ep_1')).rejects.toBeInstanceOf(StudioApiError);
    expect(calls).toBe(1);
  });

  it('maps 503 CAPABILITY_UNAVAILABLE to typed error with retryable flag', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(503, {
        type: 'about:blank',
        title: 'Capability unavailable',
        status: 503,
        detail: 'Studio run authority unavailable',
        code: 'CAPABILITY_UNAVAILABLE',
        retryable: true,
      })
    );
    const client = makeClient(fetchMock as unknown as typeof fetch);
    const err = await client.getRun('run_1').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(StudioApiError);
    const apiErr = err as StudioApiError;
    expect(apiErr.code).toBe('CAPABILITY_UNAVAILABLE');
    expect(apiErr.retryable).toBe(true);
    expect(isRetryableError(apiErr)).toBe(true);
  });

  it('maps 409 STALE_REVISION to non-retryable typed error', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(409, {
        type: 'about:blank',
        title: 'Stale revision',
        status: 409,
        detail: 'revision rev_1 is stale; server is at rev_2',
        code: 'STALE_REVISION',
        details: { current_revision_id: 'rev_2' },
      })
    );
    const client = makeClient(fetchMock as unknown as typeof fetch);
    const err = await client.recordApproval('k', 'ep_1', {
      episode_id: 'ep_1',
      revision_id: 'rev_1',
      checkpoint: 'IDEA_SELECTION',
      artifact_hash: 'a'.repeat(64),
      decision: 'APPROVED',
      expected_optimistic_version: 1,
    }).catch((e: unknown) => e);
    expect((err as StudioApiError).code).toBe('STALE_REVISION');
    expect((err as StudioApiError).details).toEqual({ current_revision_id: 'rev_2' });
    expect(isRetryableError(err)).toBe(false);
  });

  it('parses the 202 start-run resource', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(202, {
        run_id: 'run_9',
        episode_id: 'ep_1',
        resuming: false,
        run_url: '/api/v3/studio/runs/run_9',
      })
    );
    const client = makeClient(fetchMock as unknown as typeof fetch);
    const res = await client.startRun('idem_9', 'ep_1');
    expect(res.run_id).toBe('run_9');
    expect(res.resuming).toBe(false);
  });

  it('sends actor header when configured', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { episode_id: 'ep_1', checkpoint: 'C', next_state: 'DRAFT', awaiting_approval: true })
    );
    const client = new HttpStudioApiClient({
      baseUrl: 'http://studio.test',
      actor: 'reviewer-1',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });
    await client.recordApproval('k', 'ep_1', {
      episode_id: 'ep_1',
      revision_id: 'rev_1',
      checkpoint: 'IDEA_SELECTION',
      artifact_hash: 'a'.repeat(64),
      decision: 'APPROVED',
      expected_optimistic_version: 1,
    });
    const [, init] = fetchMock.mock.calls[0] as unknown as FetchCall;
    expect((init?.headers as Record<string, string> | undefined)?.['X-WindAgent-Actor']).toBe('reviewer-1');
  });
});
