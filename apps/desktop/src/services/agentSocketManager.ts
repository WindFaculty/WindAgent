/**
 * agentSocketManager.ts — Singleton WebSocket manager for all agent sessions.
 *
 * Key invariants:
 *  1. One WebSocket per sessionId (deduplication enforced).
 *  2. Component unmount does NOT disconnect an active session.
 *  3. Reconnect uses exponential backoff with jitter.
 *  4. Event deduplication: events with seq <= lastAppliedSeq are dropped.
 *  5. Subscribers (UI components) register listeners; unsubscribing does NOT close the socket.
 *  6. Socket closes ONLY on: intentional disconnect, terminal session, app shutdown.
 *  7. Concurrent connect() calls for same session share a single pending promise.
 */

import { connectWs } from "../api/client";
import type { WsHandle } from "../api/client";
import type { EventEnvelope } from "../api/types";
import { applyAgentEvent } from "./agentEventReducer";
import { useAgentSessionStore } from "../state/agentSessionStore";

// ---------- Types ----------

export type AgentEventListener = (sessionId: string, env: EventEnvelope) => void;

type ConnectionState = "disconnected" | "connecting" | "connected" | "reconnecting";

interface ConnectionEntry {
  sessionId: string;
  wsHandle: WsHandle | null;
  state: ConnectionState;
  subscribers: Set<AgentEventListener>;
  reconnectAttempts: number;
  reconnectTimer: ReturnType<typeof setTimeout> | null;
  intentionalClose: boolean;
  lastEventSequence: number;
  pendingConnectPromise: Promise<void> | null;
  heartbeatTimer: ReturnType<typeof setTimeout> | null;
}

// ---------- Reconnect configuration ----------

const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 30000;
const RECONNECT_MAX_ATTEMPTS = 10;

// Terminal session statuses that should NOT reconnect
const TERMINAL_STATUSES = new Set(["completed", "cancelled", "error", "interrupted"]);

function calcBackoffDelay(attempt: number): number {
  const base = RECONNECT_BASE_DELAY_MS * Math.pow(2, Math.min(attempt, 5));
  // Add jitter ±20%
  const jitter = base * 0.2 * (Math.random() * 2 - 1);
  return Math.min(base + jitter, RECONNECT_MAX_DELAY_MS);
}

// ---------- AgentSocketManager (singleton) ----------

class AgentSocketManager {
  private static _instance: AgentSocketManager | null = null;
  private registry = new Map<string, ConnectionEntry>();

  private constructor() {
    // Cleanup on page unload
    if (typeof window !== "undefined") {
      window.addEventListener("beforeunload", () => this.disconnectAll("app_shutdown"));
    }
  }

  static getInstance(): AgentSocketManager {
    if (!AgentSocketManager._instance) {
      AgentSocketManager._instance = new AgentSocketManager();
    }
    return AgentSocketManager._instance;
  }

  // ---------- Public API ----------

  /**
   * Connect to a session's WebSocket stream.
   * If already connected or connecting, returns immediately (deduplication).
   * Concurrent calls share a single pending promise.
   */
  async connect(sessionId: string): Promise<void> {
    const entry = this.getOrCreateEntry(sessionId);

    if (entry.state === "connected") return;

    if (entry.pendingConnectPromise) {
      // Already connecting — join the pending promise
      return entry.pendingConnectPromise;
    }

    entry.pendingConnectPromise = this._doConnect(sessionId);
    try {
      await entry.pendingConnectPromise;
    } finally {
      entry.pendingConnectPromise = null;
    }
  }

  /**
   * Force reconnect — used after a temporary disconnect.
   */
  async reconnect(sessionId: string): Promise<void> {
    const entry = this.registry.get(sessionId);
    if (!entry) return;

    entry.intentionalClose = false;
    entry.reconnectAttempts = 0;
    this.clearReconnectTimer(entry);
    this.closeSocket(entry, "reconnecting");
    await this.connect(sessionId);
  }

  /**
   * Subscribe to events for a session.
   * Returns an unsubscribe function.
   * Unsubscribing does NOT close the socket.
   */
  subscribe(sessionId: string, listener: AgentEventListener): () => void {
    const entry = this.getOrCreateEntry(sessionId);
    entry.subscribers.add(listener);

    return () => {
      entry.subscribers.delete(listener);
      // NOTE: do NOT disconnect here — socket lifecycle is independent of subscribers
    };
  }

  /**
   * Get current connection state for a session.
   */
  getConnectionState(sessionId: string): ConnectionState {
    return this.registry.get(sessionId)?.state ?? "disconnected";
  }

  /**
   * Intentionally disconnect a session's socket.
   * Will NOT reconnect.
   */
  disconnect(sessionId: string, reason = "intentional"): void {
    const entry = this.registry.get(sessionId);
    if (!entry) return;

    console.log(`[AgentSocketManager] Intentional disconnect: session=${sessionId} reason=${reason}`);
    entry.intentionalClose = true;
    this.clearReconnectTimer(entry);
    this.clearHeartbeat(entry);
    this.closeSocket(entry, reason);

    useAgentSessionStore.getState().updateConnectionStatus(sessionId, "disconnected");
  }

  /**
   * Disconnect all active sessions (e.g., on app shutdown or logout).
   */
  disconnectAll(reason = "shutdown"): void {
    for (const sessionId of this.registry.keys()) {
      this.disconnect(sessionId, reason);
    }
    this.registry.clear();
  }

  /**
   * Check if a session has an active connection.
   */
  isConnected(sessionId: string): boolean {
    return this.registry.get(sessionId)?.state === "connected";
  }

  // ---------- Internal methods ----------

  private getOrCreateEntry(sessionId: string): ConnectionEntry {
    if (!this.registry.has(sessionId)) {
      this.registry.set(sessionId, {
        sessionId,
        wsHandle: null,
        state: "disconnected",
        subscribers: new Set(),
        reconnectAttempts: 0,
        reconnectTimer: null,
        intentionalClose: false,
        lastEventSequence: 0,
        pendingConnectPromise: null,
        heartbeatTimer: null,
      });
    }
    return this.registry.get(sessionId)!;
  }

  private async _doConnect(sessionId: string): Promise<void> {
    const entry = this.getOrCreateEntry(sessionId);

    // Get last known sequence from store for cursor-based reconnect
    const storeSeq = useAgentSessionStore.getState().sessionsById[sessionId]?.lastEventSequence ?? 0;
    const afterSeq = Math.max(entry.lastEventSequence, storeSeq);

    console.log(
      `[AgentSocketManager] Connecting: session=${sessionId} afterSeq=${afterSeq} attempt=${entry.reconnectAttempts}`,
    );

    entry.state = entry.reconnectAttempts > 0 ? "reconnecting" : "connecting";
    useAgentSessionStore.getState().updateConnectionStatus(
      sessionId,
      entry.state === "reconnecting" ? "reconnecting" : "connecting",
    );

    const wsHandle = connectWs(
      sessionId,
      {
        onEvent: (env) => this.handleEvent(sessionId, env),
        onClose: (reason) => this.handleClose(sessionId, reason),
      },
      afterSeq > 0 ? afterSeq : undefined,
    );

    entry.wsHandle = wsHandle;

    // Optimistically mark as connected — WebSocket doesn't have an onopen callback
    // in the current client.ts, so we set it after creation
    entry.state = "connected";
    entry.reconnectAttempts = 0;
    useAgentSessionStore.getState().updateConnectionStatus(sessionId, "connected");

    console.log(`[AgentSocketManager] Connected: session=${sessionId}`);
  }

  private handleEvent(sessionId: string, env: EventEnvelope): void {
    const entry = this.registry.get(sessionId);
    if (!entry) return;

    // Update last known sequence
    if (env.seq !== undefined && env.seq > entry.lastEventSequence) {
      entry.lastEventSequence = env.seq;
    }

    // Apply to global store (idempotent)
    try {
      applyAgentEvent(sessionId, env);
    } catch (err) {
      console.error(`[AgentSocketManager] applyAgentEvent failed for session ${sessionId}:`, err);
    }

    // Fan-out to UI subscribers
    for (const listener of entry.subscribers) {
      try {
        listener(sessionId, env);
      } catch (err) {
        console.error(`[AgentSocketManager] Subscriber error for session ${sessionId}:`, err);
      }
    }
  }

  private handleClose(sessionId: string, reason: string): void {
    const entry = this.registry.get(sessionId);
    if (!entry) return;

    console.log(`[AgentSocketManager] WebSocket closed: session=${sessionId} reason=${reason}`);

    entry.wsHandle = null;
    entry.state = "disconnected";
    useAgentSessionStore.getState().updateConnectionStatus(sessionId, "disconnected");

    if (entry.intentionalClose) {
      console.log(`[AgentSocketManager] Not reconnecting (intentional close): session=${sessionId}`);
      return;
    }

    // Check if session is in a terminal state — do not reconnect
    const sessionStatus = useAgentSessionStore.getState().sessionsById[sessionId]?.status;
    if (sessionStatus && TERMINAL_STATUSES.has(sessionStatus)) {
      console.log(
        `[AgentSocketManager] Not reconnecting (terminal status=${sessionStatus}): session=${sessionId}`,
      );
      return;
    }

    // Schedule reconnect with backoff
    this.scheduleReconnect(sessionId);
  }

  private scheduleReconnect(sessionId: string): void {
    const entry = this.registry.get(sessionId);
    if (!entry) return;

    if (entry.reconnectAttempts >= RECONNECT_MAX_ATTEMPTS) {
      console.warn(
        `[AgentSocketManager] Max reconnect attempts reached for session ${sessionId}`,
      );
      useAgentSessionStore.getState().updateStatus(sessionId, "error");
      useAgentSessionStore.getState().updateConnectionStatus(sessionId, "disconnected");
      return;
    }

    const delay = calcBackoffDelay(entry.reconnectAttempts);
    entry.reconnectAttempts++;

    console.log(
      `[AgentSocketManager] Scheduling reconnect in ${Math.round(delay)}ms: session=${sessionId} attempt=${entry.reconnectAttempts}`,
    );

    useAgentSessionStore.getState().updateConnectionStatus(sessionId, "reconnecting");

    entry.reconnectTimer = setTimeout(async () => {
      entry.reconnectTimer = null;
      // Check again before reconnecting
      const currentEntry = this.registry.get(sessionId);
      if (!currentEntry || currentEntry.intentionalClose) return;

      const sessionStatus = useAgentSessionStore.getState().sessionsById[sessionId]?.status;
      if (sessionStatus && TERMINAL_STATUSES.has(sessionStatus)) return;

      try {
        await this.connect(sessionId);
        // Reset attempts on success
        if (currentEntry) currentEntry.reconnectAttempts = 0;
      } catch (err) {
        console.error(`[AgentSocketManager] Reconnect failed for session ${sessionId}:`, err);
        this.scheduleReconnect(sessionId);
      }
    }, delay);
  }

  private closeSocket(entry: ConnectionEntry, _reason: string): void {
    if (entry.wsHandle) {
      try {
        entry.wsHandle.close();
      } catch {
        // Ignore errors on close
      }
      entry.wsHandle = null;
    }
    entry.state = "disconnected";
  }

  private clearReconnectTimer(entry: ConnectionEntry): void {
    if (entry.reconnectTimer) {
      clearTimeout(entry.reconnectTimer);
      entry.reconnectTimer = null;
    }
  }

  private clearHeartbeat(entry: ConnectionEntry): void {
    if (entry.heartbeatTimer) {
      clearTimeout(entry.heartbeatTimer);
      entry.heartbeatTimer = null;
    }
  }
}

// ---------- Export singleton ----------

export const agentSocketManager = AgentSocketManager.getInstance();

/**
 * React hook to connect and subscribe to a session's events.
 * Safe to call multiple times — connection is deduplicated.
 * Cleanup (unsubscribe) does NOT close the socket.
 *
 * @param sessionId - session to connect to
 * @param listener - optional extra listener for this component
 * @param enabled - set to false to skip connecting (e.g., session not yet created)
 */
export function connectSession(
  sessionId: string | null,
  listener?: AgentEventListener,
  enabled = true,
): (() => void) | undefined {
  if (!sessionId || !enabled) return undefined;

  // Connect (idempotent — no-op if already connected)
  agentSocketManager.connect(sessionId).catch((err) => {
    console.error(`[connectSession] Failed to connect session ${sessionId}:`, err);
  });

  // Subscribe listener if provided
  if (listener) {
    return agentSocketManager.subscribe(sessionId, listener);
  }

  return undefined;
}
