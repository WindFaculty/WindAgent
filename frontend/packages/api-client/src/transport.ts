/**
 * HttpTransport — Core typed transport engine for @windagent/api-client.
 */

import type { ApiProblem } from '@windagent/api-contracts';
import { ApiError, HttpError, NetworkError, TimeoutError } from './errors';

export interface TransportOptions {
  baseUrl: string;
  defaultTimeoutMs?: number;
  fetchImpl?: typeof fetch;
  getCorrelationId?: () => string | null | undefined;
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD';
  path: string;
  query?: Record<string, unknown>;
  body?: unknown;
  headers?: Record<string, string>;
  idempotencyKey?: string;
  timeoutMs?: number;
  signal?: AbortSignal;
  retryOnNetworkError?: boolean;
}

export class HttpTransport {
  readonly baseUrl: string;
  readonly defaultTimeoutMs: number;
  private readonly fetchFn: typeof fetch;
  private readonly getCorrelationId?: () => string | null | undefined;

  constructor(options: TransportOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.defaultTimeoutMs = options.defaultTimeoutMs ?? 15000;
    this.fetchFn = options.fetchImpl ?? (typeof window !== 'undefined' ? window.fetch.bind(window) : fetch);
    this.getCorrelationId = options.getCorrelationId;
  }

  private buildUrl(path: string, query?: Record<string, unknown>): string {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const url = new URL(`${this.baseUrl}${cleanPath}`);
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined && value !== null) {
          url.searchParams.append(key, String(value));
        }
      }
    }
    return url.toString();
  }

  async request<T>(options: RequestOptions): Promise<T> {
    const method = options.method ?? 'GET';
    const isGet = method === 'GET';
    const isIdempotentMutation = Boolean(options.idempotencyKey);
    const retryAllowed = options.retryOnNetworkError ?? (isGet || isIdempotentMutation);
    const timeoutMs = options.timeoutMs ?? this.defaultTimeoutMs;

    const url = this.buildUrl(options.path, options.query);
    const headers: Record<string, string> = {
      Accept: 'application/json, application/problem+json',
      ...options.headers,
    };

    if (options.body !== undefined && method !== 'GET' && method !== 'HEAD') {
      headers['Content-Type'] = 'application/json';
    }

    // Attach Idempotency Key for mutations if provided
    if (options.idempotencyKey) {
      headers['Idempotency-Key'] = options.idempotencyKey;
    }

    // Attach Correlation ID
    const correlationId = this.getCorrelationId ? this.getCorrelationId() : null;
    if (correlationId && !headers['X-Correlation-ID']) {
      headers['X-Correlation-ID'] = correlationId;
    }

    const executeAttempt = async (): Promise<T> => {
      const controller = new AbortController();
      let timedOut = false;

      const timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeoutMs);

      // Chain caller's abort signal if supplied
      if (options.signal) {
        options.signal.addEventListener('abort', () => controller.abort(), { once: true });
      }

      try {
        const response = await this.fetchFn(url, {
          method,
          headers,
          body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
          signal: controller.signal,
        });

        clearTimeout(timer);

        // 204 No Content
        if (response.status === 204) {
          return undefined as unknown as T;
        }

        // Handle error responses
        if (!response.ok) {
          const contentType = response.headers.get('content-type') || '';
          if (contentType.includes('application/problem+json') || contentType.includes('application/json')) {
            try {
              const problemJson = (await response.json()) as ApiProblem;
              if (problemJson && (problemJson.code || problemJson.title)) {
                throw new ApiError(problemJson);
              }
            } catch (err) {
              if (err instanceof ApiError) throw err;
            }
          }
          const text = await response.text().catch(() => '');
          throw new HttpError(response.status, response.statusText, text);
        }

        return (await response.json()) as T;
      } catch (err: unknown) {
        clearTimeout(timer);
        if (timedOut) {
          throw new TimeoutError(timeoutMs);
        }
        if (err instanceof ApiError || err instanceof HttpError || err instanceof TimeoutError) {
          throw err;
        }
        throw new NetworkError(err instanceof Error ? err.message : 'Network request failed');
      }
    };

    try {
      return await executeAttempt();
    } catch (err) {
      if (retryAllowed && err instanceof NetworkError && !(err instanceof TimeoutError)) {
        return await executeAttempt();
      }
      throw err;
    }
  }

  get<T>(path: string, query?: Record<string, unknown>, options?: Partial<RequestOptions>): Promise<T> {
    return this.request<T>({ ...options, method: 'GET', path, query });
  }

  post<T>(path: string, body?: unknown, options?: Partial<RequestOptions>): Promise<T> {
    return this.request<T>({ ...options, method: 'POST', path, body });
  }

  patch<T>(path: string, body?: unknown, options?: Partial<RequestOptions>): Promise<T> {
    return this.request<T>({ ...options, method: 'PATCH', path, body });
  }

  put<T>(path: string, body?: unknown, options?: Partial<RequestOptions>): Promise<T> {
    return this.request<T>({ ...options, method: 'PUT', path, body });
  }

  delete<T>(path: string, options?: Partial<RequestOptions>): Promise<T> {
    return this.request<T>({ ...options, method: 'DELETE', path });
  }
}
