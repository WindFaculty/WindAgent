/**
 * Owns exactly one reconnecting WebSocket for each conversation. Components
 * subscribe to the manager; they never open their own stream.
 */
import { connectConversationWs, type WsHandle } from "../api/client";
import type { ConversationEventEnvelope } from "../api/types";

export const CONVERSATION_RECONNECT_BASE_DELAY_MS = 1_000;
export const CONVERSATION_RECONNECT_MAX_DELAY_MS = 30_000;
export const CONVERSATION_RECONNECT_MAX_ATTEMPTS = 10;

/**
 * `jitter` is injectable so retry scheduling is deterministic in tests. A
 * value of 0.5 means no jitter; 0 and 1 mean -20% and +20%, respectively.
 */
export function calculateConversationReconnectDelay(
  attempt: number,
  jitter = Math.random(),
): number {
  const exponent = Math.min(Math.max(attempt - 1, 0), 5);
  const base = Math.min(
    CONVERSATION_RECONNECT_BASE_DELAY_MS * 2 ** exponent,
    CONVERSATION_RECONNECT_MAX_DELAY_MS,
  );
  const jittered = base * (0.8 + Math.max(0, Math.min(jitter, 1)) * 0.4);
  return Math.min(Math.round(jittered), CONVERSATION_RECONNECT_MAX_DELAY_MS);
}

type ConversationListener = (event: ConversationEventEnvelope) => void;

interface ConnectionEntry {
  conversationId: string;
  handle: WsHandle | null;
  listeners: Set<ConversationListener>;
  getCursor: () => number;
  reconnectAttempts: number;
  reconnectTimer: ReturnType<typeof setTimeout> | null;
  intentionalClose: boolean;
}

class ConversationSocketManager {
  private readonly entries = new Map<string, ConnectionEntry>();

  connect(conversationId: string, getCursor: () => number): void {
    const existing = this.entries.get(conversationId);
    if (existing) {
      existing.getCursor = getCursor;
      if (!existing.handle && !existing.reconnectTimer && !existing.intentionalClose) this.open(existing);
      return;
    }
    const entry: ConnectionEntry = {
      conversationId,
      handle: null,
      listeners: new Set(),
      getCursor,
      reconnectAttempts: 0,
      reconnectTimer: null,
      intentionalClose: false,
    };
    this.entries.set(conversationId, entry);
    this.open(entry);
  }

  subscribe(conversationId: string, listener: ConversationListener): () => void {
    let entry = this.entries.get(conversationId);
    if (!entry) {
      entry = {
        conversationId,
        handle: null,
        listeners: new Set(),
        getCursor: () => 0,
        reconnectAttempts: 0,
        reconnectTimer: null,
        intentionalClose: false,
      };
      this.entries.set(conversationId, entry);
    }
    entry.listeners.add(listener);
    return () => entry?.listeners.delete(listener);
  }

  disconnect(conversationId: string): void {
    const entry = this.entries.get(conversationId);
    if (!entry) return;
    entry.intentionalClose = true;
    if (entry.reconnectTimer) clearTimeout(entry.reconnectTimer);
    entry.handle?.close();
    this.entries.delete(conversationId);
  }

  disconnectAll(): void {
    for (const conversationId of [...this.entries.keys()]) this.disconnect(conversationId);
  }

  private open(entry: ConnectionEntry): void {
    entry.handle = connectConversationWs(
      entry.conversationId,
      {
        onEvent: (event) => {
          entry.reconnectAttempts = 0;
          for (const listener of entry.listeners) listener(event);
        },
        onClose: () => this.onClose(entry),
      },
      entry.getCursor(),
    );
  }

  private onClose(entry: ConnectionEntry): void {
    entry.handle = null;
    if (entry.intentionalClose || !this.entries.has(entry.conversationId)) return;
    if (entry.reconnectAttempts >= CONVERSATION_RECONNECT_MAX_ATTEMPTS) return;

    entry.reconnectAttempts += 1;
    const delay = calculateConversationReconnectDelay(entry.reconnectAttempts);
    entry.reconnectTimer = setTimeout(() => {
      entry.reconnectTimer = null;
      if (!entry.intentionalClose && this.entries.has(entry.conversationId)) this.open(entry);
    }, delay);
  }
}

export const conversationSocketManager = new ConversationSocketManager();
