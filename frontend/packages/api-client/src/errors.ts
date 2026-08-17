/**
 * Typed Error Classes for @windagent/api-client.
 */

import type { ApiProblem } from '@windagent/api-contracts';

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryable: boolean;
  readonly details?: Record<string, unknown>;
  readonly correlationId?: string | null;
  readonly typeUri: string;

  constructor(problem: ApiProblem) {
    super(problem.detail || problem.title);
    this.name = 'ApiError';
    this.code = problem.code;
    this.status = problem.status;
    this.retryable = problem.retryable === true;
    this.details = problem.details;
    this.correlationId = problem.correlation_id;
    this.typeUri = problem.type;
  }
}

export class NetworkError extends Error {
  readonly retryable = true;
  constructor(message: string) {
    super(message);
    this.name = 'NetworkError';
  }
}

export class TimeoutError extends NetworkError {
  constructor(timeoutMs: number) {
    super(`Request timed out after ${timeoutMs}ms`);
    this.name = 'TimeoutError';
  }
}

export class HttpError extends Error {
  readonly retryable: boolean;
  constructor(
    readonly status: number,
    readonly statusText: string,
    readonly responseBody?: string
  ) {
    super(`API returned HTTP ${status}${statusText ? `: ${statusText}` : ''}`);
    this.name = 'HttpError';
    this.retryable = status >= 500;
  }
}
