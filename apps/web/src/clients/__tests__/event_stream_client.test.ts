/**
 * Tests for EventStreamClient - Event stream handling with reconnection and deduplication.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

global.fetch = vi.fn();

const mockFetch = global.fetch as vi.Mock;

const mockEvent = (id: string, type: string, aggregateId: string): DomainEvent => ({
  event_id: id,
  event_type: type,
  aggregate_id: aggregateId,
  payload: { data: "test" },
  timestamp: new Date().toISOString(),
});

interface DomainEvent {
  event_id: string;
  event_type: string;
  aggregate_id: string;
  payload: Record<string, any>;
  timestamp: string;
}

import { EventStreamClient } from "../event_stream_client";

describe("EventStreamClient", () => {
  let client: EventStreamClient;

  beforeEach(() => {
    vi.clearAllMocks();
    client = new EventStreamClient("http://localhost:8000");
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe("initial state", () => {
    it("should start disconnected", () => {
      expect(client.connected).toBe(false);
    });

    it("should have empty dedupe cache", () => {
      expect(client.getDedupeCacheSize()).toBe(0);
    });
  });

  describe("fetchEventStream", () => {
    it("should fetch events and mark connected", async () => {
      const events = [mockEvent("evt-1", "task.created", "task-1")];
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(events),
      });

      const result = await client.fetchEventStream("task-1");

      expect(result).toEqual(events);
      expect(client.connected).toBe(true);
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/v2/events?aggregate_id=task-1"
      );
    });

    it("should fetch without aggregate ID when not provided", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([]),
      });

      await client.fetchEventStream();

      expect(mockFetch).toHaveBeenCalledWith("http://localhost:8000/api/v2/events");
    });

    it("should deduplicate events by event_id", async () => {
      const event = mockEvent("evt-1", "task.created", "task-1");
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve([event]),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve([event, mockEvent("evt-2", "task.updated", "task-1")]),
        });

      await client.fetchEventStream("task-1");
      const result = await client.fetchEventStream("task-1");

      expect(result).toHaveLength(1);
      expect(result[0].event_id).toBe("evt-2");
      expect(client.getDedupeCacheSize()).toBe(2);
    });

    it("should suppress duplicate events across calls", async () => {
      const events = [mockEvent("evt-1", "task.created", "task-1")];
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(events),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(events),
        });

      await client.fetchEventStream("task-1");
      const result = await client.fetchEventStream("task-1");

      expect(result).toHaveLength(0);
    });

    it("should handle malformed event (missing event_id)", async () => {
      const malformedEvent = { event_type: "task.created", aggregate_id: "task-1", payload: {} };
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([malformedEvent]),
      });

      await expect(client.fetchEventStream("task-1")).rejects.toThrow("Malformed event: missing event_id");
    });

    it("should throw on HTTP error", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        statusText: "Not Found",
      });

      await expect(client.fetchEventStream("task-1")).rejects.toThrow("Event stream error: Not Found");
    });

    it("should handle out-of-order events", async () => {
      const evt1 = mockEvent("evt-3", "task.updated", "task-1");
      const evt2 = mockEvent("evt-1", "task.created", "task-1");
      const evt3 = mockEvent("evt-2", "task.started", "task-1");

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([evt1, evt2, evt3]),
      });

      const result = await client.fetchEventStream("task-1");
      expect(result).toHaveLength(3);
    });

    it("should notify subscribers on new events", async () => {
      const event = mockEvent("evt-1", "task.created", "task-1");
      const listener = vi.fn();
      const unsubscribe = client.subscribe(listener);

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([event]),
      });

      await client.fetchEventStream("task-1");

      expect(listener).toHaveBeenCalledWith(event);
      expect(listener).toHaveBeenCalledTimes(1);

      unsubscribe();

      // Need to mock fetch again for second call after unsubscribe
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([mockEvent("evt-2", "task.updated", "task-1")]),
      });

      await client.fetchEventStream("task-1");
      expect(listener).toHaveBeenCalledTimes(1);
    });
  });

  describe("reconnection", () => {
    it("should handle disconnect and reconnect", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([mockEvent("evt-1", "task.created", "task-1")]),
      });

      await client.fetchEventStream("task-1");
      expect(client.connected).toBe(true);

      client.handleDisconnect();
      expect(client.connected).toBe(false);

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([mockEvent("evt-2", "task.updated", "task-1")]),
      });

      const result = await client.fetchEventStream("task-1");
      expect(client.connected).toBe(true);
      expect(result[0].event_id).toBe("evt-2");
    });

    it("should preserve dedupe cache across disconnect", async () => {
      const event = mockEvent("evt-1", "task.created", "task-1");
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([event]),
      });

      await client.fetchEventStream("task-1");
      client.handleDisconnect();

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([event]),
      });

      const result = await client.fetchEventStream("task-1");
      expect(result).toHaveLength(0);
      expect(client.getDedupeCacheSize()).toBe(1);
    });
  });

  describe("clearDedupeCache", () => {
    it("should clear dedupe cache", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([mockEvent("evt-1", "task.created", "task-1")]),
      });

      await client.fetchEventStream("task-1");
      expect(client.getDedupeCacheSize()).toBe(1);

      client.clearDedupeCache();
      expect(client.getDedupeCacheSize()).toBe(0);
    });

    it("should allow re-processing events after cache clear", async () => {
      const event = mockEvent("evt-1", "task.created", "task-1");
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve([event]),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve([event]),
        });

      await client.fetchEventStream("task-1");
      client.clearDedupeCache();
      const result = await client.fetchEventStream("task-1");

      expect(result).toHaveLength(1);
      expect(result[0].event_id).toBe("evt-1");
    });
  });

  describe("backoff and retry behavior", () => {
    it("should handle connection failure gracefully", async () => {
      mockFetch.mockRejectedValueOnce(new Error("Network error"));

      await expect(client.fetchEventStream("task-1")).rejects.toThrow("Network error");
      expect(client.connected).toBe(false);
    });
  });
});
