/**
 * RealtimeClient — Resilient WebSocket / Event stream client with sequence resumption.
 */

import type { EventEnvelope } from '@windagent/api-contracts';
import type {
  EventHandler,
  RealtimeConnectionState,
  RealtimeOptions,
  StateChangeHandler,
  SubscriptionSpec,
} from './types';

export class RealtimeClient {
  private state: RealtimeConnectionState = 'DISCONNECTED';
  private socket: WebSocket | null = null;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private isIntentionallyClosed = false;

  private subscriptions = new Map<string, { spec: SubscriptionSpec; handlers: Set<EventHandler<any>> }>();
  private stateListeners = new Set<StateChangeHandler>();
  private lastProcessedSequences = new Map<string, number>();

  readonly options: Required<RealtimeOptions>;

  constructor(options: RealtimeOptions) {
    this.options = {
      url: options.url,
      heartbeatIntervalMs: options.heartbeatIntervalMs ?? 30000,
      reconnectBaseDelayMs: options.reconnectBaseDelayMs ?? 1000,
      reconnectMaxDelayMs: options.reconnectMaxDelayMs ?? 30000,
      maxReconnectAttempts: options.maxReconnectAttempts ?? 10,
      getAuthToken: options.getAuthToken ?? (() => null),
    };
  }

  getState(): RealtimeConnectionState {
    return this.state;
  }

  onStateChange(handler: StateChangeHandler): () => void {
    this.stateListeners.add(handler);
    handler(this.state);
    return () => this.stateListeners.delete(handler);
  }

  private setState(nextState: RealtimeConnectionState) {
    if (this.state !== nextState) {
      this.state = nextState;
      for (const listener of this.stateListeners) {
        try {
          listener(nextState);
        } catch {
          // ignore listener errors
        }
      }
    }
  }

  async connect(): Promise<void> {
    if (this.state === 'CONNECTED' || this.state === 'CONNECTING') return;

    this.isIntentionallyClosed = false;
    this.setState('CONNECTING');

    try {
      const token = await this.options.getAuthToken();
      const wsUrl = new URL(this.options.url);
      if (token) {
        wsUrl.searchParams.set('token', token);
      }

      // Check environment
      if (typeof WebSocket === 'undefined') {
        this.setState('DEGRADED');
        return;
      }

      this.socket = new WebSocket(wsUrl.toString());

      this.socket.onopen = () => {
        this.setState('CONNECTED');
        this.reconnectAttempt = 0;
        this.startHeartbeat();
        this.resubscribeAll();
      };

      this.socket.onmessage = (event: MessageEvent) => {
        try {
          const envelope = JSON.parse(event.data) as EventEnvelope;
          this.handleIncomingEvent(envelope);
        } catch {
          // Ignore invalid messages
        }
      };

      this.socket.onclose = () => {
        this.stopHeartbeat();
        this.socket = null;
        if (!this.isIntentionallyClosed) {
          this.setState('DISCONNECTED');
          this.scheduleReconnect();
        }
      };

      this.socket.onerror = () => {
        this.setState('DEGRADED');
      };
    } catch {
      this.setState('DISCONNECTED');
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    this.isIntentionallyClosed = true;
    this.stopHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.setState('DISCONNECTED');
  }

  private scheduleReconnect() {
    if (this.isIntentionallyClosed || this.reconnectTimer) return;
    if (this.reconnectAttempt >= this.options.maxReconnectAttempts) {
      this.setState('DEGRADED');
      return;
    }

    const delay = Math.min(
      this.options.reconnectBaseDelayMs * Math.pow(2, this.reconnectAttempt),
      this.options.reconnectMaxDelayMs
    );
    this.reconnectAttempt++;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        this.socket.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }));
      }
    }, this.options.heartbeatIntervalMs);
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  subscribe<T = Record<string, unknown>>(spec: SubscriptionSpec, handler: EventHandler<T>): () => void {
    const key = `${spec.aggregateType}:${spec.aggregateId || '*'}`;
    let sub = this.subscriptions.get(key);
    if (!sub) {
      sub = { spec, handlers: new Set() };
      this.subscriptions.set(key, sub);
      this.sendSubscription(spec);
    }
    sub.handlers.add(handler);

    return () => {
      sub?.handlers.delete(handler);
      if (sub && sub.handlers.size === 0) {
        this.subscriptions.delete(key);
        this.sendUnsubscription(spec);
      }
    };
  }

  private sendSubscription(spec: SubscriptionSpec) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      const key = `${spec.aggregateType}:${spec.aggregateId || '*'}`;
      const lastSeq = this.lastProcessedSequences.get(key) ?? spec.afterSequence;
      this.socket.send(JSON.stringify({
        type: 'subscribe',
        aggregate_type: spec.aggregateType,
        aggregate_id: spec.aggregateId,
        after_sequence: lastSeq,
      }));
    }
  }

  private sendUnsubscription(spec: SubscriptionSpec) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({
        type: 'unsubscribe',
        aggregate_type: spec.aggregateType,
        aggregate_id: spec.aggregateId,
      }));
    }
  }

  private resubscribeAll() {
    for (const { spec } of this.subscriptions.values()) {
      this.sendSubscription(spec);
    }
  }

  private handleIncomingEvent(envelope: EventEnvelope<any>) {
    if (!envelope || !envelope.event_type) return;

    const streamKey = `${envelope.aggregate_type || 'global'}:${envelope.aggregate_id || '*'}`;
    const lastSeq = this.lastProcessedSequences.get(streamKey) ?? 0;

    // Deduplication check: drop duplicate sequence numbers
    if (envelope.sequence > 0 && envelope.sequence <= lastSeq) {
      return;
    }

    if (envelope.sequence > 0) {
      this.lastProcessedSequences.set(streamKey, envelope.sequence);
    }

    // Match exact aggregate and wildcard subscriptions
    const directKey = `${envelope.aggregate_type}:${envelope.aggregate_id}`;
    const wildcardKey = `${envelope.aggregate_type}:*`;

    const targetSubs = [this.subscriptions.get(directKey), this.subscriptions.get(wildcardKey)].filter(Boolean);

    for (const sub of targetSubs) {
      if (sub) {
        for (const handler of sub.handlers) {
          try {
            handler(envelope);
          } catch {
            // suppress callback error
          }
        }
      }
    }
  }
}

export function createRealtimeClient(options: RealtimeOptions): RealtimeClient {
  return new RealtimeClient(options);
}
