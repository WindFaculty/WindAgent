import { describe, it, expect, vi } from 'vitest';
import { HttpTransport } from '../transport';
import { ApiError, NetworkError, TimeoutError, HttpError } from '../errors';

describe('HttpTransport', () => {
  it('sends GET request, formats query params, and parses JSON', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'proj_123', name: 'Test' }),
      headers: new Headers({ 'content-type': 'application/json' }),
    });

    const transport = new HttpTransport({
      baseUrl: 'http://localhost:8000',
      fetchImpl: mockFetch as unknown as typeof fetch,
    });

    const result = await transport.get<{ id: string; name: string }>('/api/v3/projects/proj_123', {
      limit: 10,
      active: true,
    });
    expect(result.id).toBe('proj_123');
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v3/projects/proj_123?limit=10&active=true',
      expect.objectContaining({ method: 'GET' })
    );
  });

  it('attaches Idempotency-Key and Correlation-ID headers', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: 'proj_new' }),
      headers: new Headers({ 'content-type': 'application/json' }),
    });

    const transport = new HttpTransport({
      baseUrl: 'http://localhost:8000',
      fetchImpl: mockFetch as unknown as typeof fetch,
      getCorrelationId: () => 'corr_abc_999',
    });

    await transport.post('/api/v3/projects', { name: 'New Project' }, { idempotencyKey: 'idem_key_1' });

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v3/projects',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Idempotency-Key': 'idem_key_1',
          'X-Correlation-ID': 'corr_abc_999',
          'Content-Type': 'application/json',
        }),
      })
    );
  });

  it('maps ApiProblem RFC 7807 response to ApiError', async () => {
    const problemPayload = {
      type: 'https://windagent.dev/problems/version-conflict',
      title: 'Version Conflict',
      status: 409,
      detail: 'Expected version mismatch',
      code: 'VERSION_CONFLICT',
      correlation_id: 'corr_test_01',
      retryable: false,
      details: { current_version: 3, expected_version: 1 },
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      headers: new Headers({ 'content-type': 'application/problem+json' }),
      json: async () => problemPayload,
    });

    const transport = new HttpTransport({
      baseUrl: 'http://localhost:8000',
      fetchImpl: mockFetch as unknown as typeof fetch,
    });

    let caughtError: ApiError | null = null;
    try {
      await transport.patch('/api/v3/projects/1', { expected_version: 1 });
    } catch (err) {
      if (err instanceof ApiError) {
        caughtError = err;
      }
    }

    expect(caughtError).not.toBeNull();
    expect(caughtError?.status).toBe(409);
    expect(caughtError?.code).toBe('VERSION_CONFLICT');
    expect(caughtError?.correlationId).toBe('corr_test_01');
    expect(caughtError?.details).toEqual({ current_version: 3, expected_version: 1 });
  });

  it('retries GET requests once on network failure', async () => {
    let callCount = 0;
    const mockFetch = vi.fn().mockImplementation(async () => {
      callCount++;
      if (callCount === 1) {
        throw new Error('Connection refused');
      }
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ status: 'ok' }),
      };
    });

    const transport = new HttpTransport({
      baseUrl: 'http://localhost:8000',
      fetchImpl: mockFetch as unknown as typeof fetch,
    });

    const res = await transport.get<{ status: string }>('/health');
    expect(res.status).toBe('ok');
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('retries POST requests on network failure if Idempotency-Key is provided', async () => {
    let callCount = 0;
    const mockFetch = vi.fn().mockImplementation(async () => {
      callCount++;
      if (callCount === 1) {
        throw new Error('Network timeout');
      }
      return {
        ok: true,
        status: 201,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ id: 'new_id' }),
      };
    });

    const transport = new HttpTransport({
      baseUrl: 'http://localhost:8000',
      fetchImpl: mockFetch as unknown as typeof fetch,
    });

    const res = await transport.post<{ id: string }>('/api/v3/items', { foo: 'bar' }, { idempotencyKey: 'idem_key_safe' });
    expect(res.id).toBe('new_id');
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('does NOT retry POST requests without Idempotency-Key on network failure', async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error('Network reset'));

    const transport = new HttpTransport({
      baseUrl: 'http://localhost:8000',
      fetchImpl: mockFetch as unknown as typeof fetch,
    });

    await expect(transport.post('/api/v3/items', { foo: 'bar' })).rejects.toThrow(NetworkError);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('handles 204 No Content gracefully', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers(),
    });

    const transport = new HttpTransport({
      baseUrl: 'http://localhost:8000',
      fetchImpl: mockFetch as unknown as typeof fetch,
    });

    const result = await transport.delete('/api/v3/projects/proj_old');
    expect(result).toBeUndefined();
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('throws HttpError when server returns non-problem error status', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
      headers: new Headers({ 'content-type': 'text/plain' }),
      text: async () => 'upstream server error',
    });

    const transport = new HttpTransport({
      baseUrl: 'http://localhost:8000',
      fetchImpl: mockFetch as unknown as typeof fetch,
    });

    await expect(transport.get('/api/v3/projects')).rejects.toThrow(HttpError);
  });
});
