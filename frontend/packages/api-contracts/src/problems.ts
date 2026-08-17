/**
 * RFC 7807 Problem Details for HTTP APIs (ApiProblem).
 */

export interface ApiProblem {
  type: string;
  title: string;
  status: number;
  detail: string;
  code: string;
  correlation_id?: string | null;
  retryable?: boolean;
  details?: Record<string, unknown>;
}

export type ApiErrorCode =
  | 'VALIDATION_FAILED'
  | 'NOT_FOUND'
  | 'PERMISSION_DENIED'
  | 'VERSION_CONFLICT'
  | 'REVISION_CONFLICT'
  | 'IDEMPOTENCY_CONFLICT'
  | 'CAPABILITY_UNAVAILABLE'
  | 'INTERNAL_ERROR'
  | string;
