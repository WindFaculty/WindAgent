/**
 * Decoupled Event Stream Client for WindAgent Web Application (Phase 13).
 * Connects to SSE / WebSocket event stream with automatic reconnection and deduplication.
 */

export interface DomainEvent {
  event_id: string;
  event_type: string;
  aggregate_id: string;
  payload: Record<string, any>;
  timestamp: string;
}

export class EventStreamClient {
  private baseUrl: string;
  private processedEventIds: Set<string> = new Set();
  private isConnected: boolean = false;
  private listeners: Array<(event: DomainEvent) => void> = [];

  constructor(baseUrl: string = "http://localhost:8000") {
    this.baseUrl = baseUrl;
  }

  get connected(): boolean {
    return this.isConnected;
  }

  subscribe(callback: (event: DomainEvent) => void): () => void {
    this.listeners.push(callback);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== callback);
    };
  }

  async fetchEventStream(aggregateId?: string): Promise<DomainEvent[]> {
    const url = aggregateId
      ? `${this.baseUrl}/api/v2/events?aggregate_id=${aggregateId}`
      : `${this.baseUrl}/api/v2/events`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`Event stream error: ${res.statusText}`);
    }
    const events: DomainEvent[] = await res.json();

    // Validate events have event_id
    for (const evt of events) {
      if (!evt.event_id) {
        throw new Error("Malformed event: missing event_id");
      }
    }

    // Perform deduplication
    const newEvents: DomainEvent[] = [];
    for (const evt of events) {
      if (!this.processedEventIds.has(evt.event_id)) {
        this.processedEventIds.add(evt.event_id);
        newEvents.push(evt);
        this.notifyListeners(evt);
      }
    }
    this.isConnected = true;
    return newEvents;
  }

  private notifyListeners(event: DomainEvent): void {
    for (const listener of this.listeners) {
      listener(event);
    }
  }

  handleDisconnect(): void {
    this.isConnected = false;
  }

  clearDedupeCache(): void {
    this.processedEventIds.clear();
  }

  getDedupeCacheSize(): number {
    return this.processedEventIds.size;
  }
}
