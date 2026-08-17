/**
 * Realtime types and connection state definitions.
 */

import type { EventEnvelope } from '@windagent/api-contracts';

export type RealtimeConnectionState =
  | 'DISCONNECTED'
  | 'CONNECTING'
  | 'CONNECTED'
  | 'DEGRADED'
  | 'RESYNCING';

export interface SubscriptionSpec {
  aggregateType: string;
  aggregateId?: string;
  afterSequence?: number;
}

export type EventHandler<T = Record<string, unknown>> = (event: EventEnvelope<T>) => void;
export type StateChangeHandler = (state: RealtimeConnectionState) => void;
export type ErrorHandler = (error: Error) => void;

export interface RealtimeOptions {
  url: string;
  heartbeatIntervalMs?: number;
  reconnectBaseDelayMs?: number;
  reconnectMaxDelayMs?: number;
  maxReconnectAttempts?: number;
  getAuthToken?: () => string | null | Promise<string | null>;
}
