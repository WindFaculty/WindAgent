import { describe, expect, it } from "vitest";
import { FakeRealtimeChannel, type RealtimeEvent } from "../channel.ts";

const sampleEvent: RealtimeEvent = {
  eventId: "evt_1",
  eventType: "job.completed",
  eventVersion: 1,
  occurredAt: "2026-09-01T00:00:00Z",
  payload: { jobId: "job_42" },
};

describe("FakeRealtimeChannel", () => {
  it("delivers events to subscribers while connected", () => {
    const channel = new FakeRealtimeChannel();
    const received: RealtimeEvent[] = [];
    const unsubscribe = channel.subscribe((event) => received.push(event));

    void channel.connect();
    channel.emit(sampleEvent);
    expect(received).toHaveLength(1);
    expect(received[0]?.eventType).toBe("job.completed");

    unsubscribe();
    channel.emit(sampleEvent);
    expect(received).toHaveLength(1);
  });

  it("refuses to emit while disconnected", () => {
    const channel = new FakeRealtimeChannel();
    channel.subscribe(() => undefined);
    expect(() => channel.emit(sampleEvent)).toThrow(/disconnected/);
  });
});
