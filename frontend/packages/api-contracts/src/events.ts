/**
 * Realtime EventEnvelope Contract.
 */

export interface EventEnvelope<T = Record<string, unknown>> {
  event_id: string;
  event_type: string;
  schema_version?: number;
  stream_id?: string;
  aggregate_type?: string | null;
  aggregate_id?: string | null;
  sequence: number;
  occurred_at: string;
  recorded_at?: string | null;
  session_id?: string | null;
  correlation_id?: string | null;
  causation_id?: string | null;
  trace_id?: string | null;
  payload: T;
  metadata?: Record<string, unknown>;
}
