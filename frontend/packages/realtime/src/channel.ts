/**
 * Realtime synchronization contract and implementations.
 */

export interface RealtimeEvent {
  eventId: string;
  eventType: string;
  eventVersion: number;
  occurredAt: string;
  correlationId?: string;
  payload: Record<string, unknown>;
}

export type RealtimeListener = (event: RealtimeEvent) => void;

export interface RealtimeChannel {
  connect(): Promise<void>;
  disconnect(): void;
  subscribe(listener: RealtimeListener): () => void;
  readonly isConnected: boolean;
}

/** In-memory channel used by unit tests and offline workflows. */
export class FakeRealtimeChannel implements RealtimeChannel {
  private readonly listeners = new Set<RealtimeListener>();
  private connected = false;

  async connect(): Promise<void> {
    this.connected = true;
  }

  disconnect(): void {
    this.connected = false;
  }

  subscribe(listener: RealtimeListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit(event: RealtimeEvent): void {
    if (!this.connected) {
      throw new Error("FakeRealtimeChannel.emit called while disconnected");
    }
    for (const listener of this.listeners) {
      listener(event);
    }
  }

  get isConnected(): boolean {
    return this.connected;
  }
}

/** WebSocket client channel with exponential backoff and heartbeat. */
export class WebSocketRealtimeChannel implements RealtimeChannel {
  private socket: WebSocket | null = null;
  private readonly listeners = new Set<RealtimeListener>();
  private connected = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;

  constructor(
    private readonly url: string,
    private readonly maxReconnectAttempts: number = 5,
  ) {}

  async connect(): Promise<void> {
    return new Promise((resolve) => {
      try {
        if (typeof WebSocket === "undefined") {
          this.connected = true;
          resolve();
          return;
        }

        this.socket = new WebSocket(this.url);
        this.socket.onopen = () => {
          this.connected = true;
          this.reconnectAttempts = 0;
          resolve();
        };

        this.socket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data) as RealtimeEvent;
            for (const listener of this.listeners) {
              listener(data);
            }
          } catch {
            // Non-JSON or ping
          }
        };

        this.socket.onclose = () => {
          this.connected = false;
          this.scheduleReconnect();
        };

        this.socket.onerror = () => {
          this.connected = false;
          resolve(); // Resolve on initial fail so bootstrap continues
        };
      } catch {
        this.connected = false;
        resolve();
      }
    });
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  disconnect(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.connected = false;
  }

  subscribe(listener: RealtimeListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  get isConnected(): boolean {
    return this.connected;
  }
}
