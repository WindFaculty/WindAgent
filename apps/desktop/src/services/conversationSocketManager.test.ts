import { afterEach, describe, expect, it, vi } from "vitest";

const mockConnectConversationWs = vi.fn();

vi.mock("../api/client", () => ({
  connectConversationWs: (...args: any[]) => mockConnectConversationWs(...args),
}));

import {
  calculateConversationReconnectDelay,
  conversationSocketManager,
} from "./conversationSocketManager";

afterEach(() => {
  conversationSocketManager.disconnectAll();
  mockConnectConversationWs.mockReset();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("ConversationSocketManager", () => {
  it("uses one conversation socket and replays from the global cursor", () => {
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    const close = vi.fn();
    mockConnectConversationWs.mockImplementation(() => ({ send: vi.fn(), close }));
    let cursor = 0;

    conversationSocketManager.connect("conversation-1", () => cursor);
    conversationSocketManager.subscribe("conversation-1", (event) => {
      cursor = event.sequence;
    });
    conversationSocketManager.connect("conversation-1", () => cursor);
    expect(mockConnectConversationWs).toHaveBeenCalledTimes(1);
    expect(mockConnectConversationWs.mock.calls[0][2]).toBe(0);

    mockConnectConversationWs.mock.calls[0][1].onEvent({ sequence: 7 } as any);
    mockConnectConversationWs.mock.calls[0][1].onClose("network interrupted");
    vi.advanceTimersByTime(1_000);

    expect(mockConnectConversationWs).toHaveBeenCalledTimes(2);
    expect(mockConnectConversationWs.mock.calls[1][2]).toBe(7);
  });

  it("has deterministic capped exponential backoff with bounded jitter", () => {
    expect(calculateConversationReconnectDelay(1, 0)).toBe(800);
    expect(calculateConversationReconnectDelay(1, 0.5)).toBe(1_000);
    expect(calculateConversationReconnectDelay(6, 1)).toBe(30_000);
    expect(calculateConversationReconnectDelay(100, 0)).toBe(24_000);
  });
});
