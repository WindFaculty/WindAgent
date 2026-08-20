import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { RealtimeClient, createRealtimeClient } from '../realtimeClient';
import type { EventEnvelope } from '@windagent/api-contracts';

class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: MockWebSocket[] = [];

  readonly url: string;
  readyState = MockWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  receive(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  serverClose() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }

  send(message: string) {
    this.sent.push(message);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal('WebSocket', MockWebSocket);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('RealtimeClient', () => {
  it('initializes in DISCONNECTED state via constructor and helper', () => {
    const client = createRealtimeClient({ url: 'ws://localhost:8000/ws' });
    expect(client.getState()).toBe('DISCONNECTED');
  });

  it('notifies state change listeners on subscription', () => {
    const client = new RealtimeClient({ url: 'ws://localhost:8000/ws' });
    const states: string[] = [];
    const unsubscribe = client.onStateChange((s) => states.push(s));

    expect(states).toContain('DISCONNECTED');
    unsubscribe();
  });

  it('filters and routes incoming events to exact aggregate subscribers', () => {
    const client = new RealtimeClient({ url: 'ws://localhost:8000/ws' });
    const receivedEvents: EventEnvelope[] = [];

    const unsub = client.subscribe({ aggregateType: 'project', aggregateId: 'proj_123' }, (event) => {
      receivedEvents.push(event);
    });

    // Simulate event handling
    (client as any).handleIncomingEvent({
      event_id: 'evt_1',
      event_type: 'project.updated',
      aggregate_type: 'project',
      aggregate_id: 'proj_123',
      sequence: 1,
      occurred_at: new Date().toISOString(),
      payload: { name: 'Updated' },
    });

    expect(receivedEvents.length).toBe(1);
    expect(receivedEvents[0].payload.name).toBe('Updated');

    // Simulate event for different aggregate ID
    (client as any).handleIncomingEvent({
      event_id: 'evt_2',
      event_type: 'project.updated',
      aggregate_type: 'project',
      aggregate_id: 'proj_other',
      sequence: 2,
      occurred_at: new Date().toISOString(),
      payload: { name: 'Other' },
    });

    expect(receivedEvents.length).toBe(1);

    unsub();
  });

  it('routes incoming events to wildcard subscribers', () => {
    const client = new RealtimeClient({ url: 'ws://localhost:8000/ws' });
    const wildcardEvents: EventEnvelope[] = [];

    client.subscribe({ aggregateType: 'episode', aggregateId: '*' }, (event) => {
      wildcardEvents.push(event);
    });

    (client as any).handleIncomingEvent({
      event_id: 'evt_ep_1',
      event_type: 'episode.created',
      aggregate_type: 'episode',
      aggregate_id: 'ep_101',
      sequence: 1,
      occurred_at: new Date().toISOString(),
      payload: { title: 'Episode 1' },
    });

    (client as any).handleIncomingEvent({
      event_id: 'evt_ep_2',
      event_type: 'episode.locked',
      aggregate_type: 'episode',
      aggregate_id: 'ep_102',
      sequence: 2,
      occurred_at: new Date().toISOString(),
      payload: { title: 'Episode 2' },
    });

    expect(wildcardEvents.length).toBe(2);
    expect(wildcardEvents[0].aggregate_id).toBe('ep_101');
    expect(wildcardEvents[1].aggregate_id).toBe('ep_102');
  });

  it('drops duplicate and older sequence events (sequence <= lastProcessedSeq)', () => {
    const client = new RealtimeClient({ url: 'ws://localhost:8000/ws' });
    const received: number[] = [];

    client.subscribe({ aggregateType: 'project', aggregateId: 'proj_1' }, (event) => {
      received.push(event.sequence);
    });

    // Process sequence 10
    (client as any).handleIncomingEvent({
      event_id: 'evt_10',
      event_type: 'project.updated',
      aggregate_type: 'project',
      aggregate_id: 'proj_1',
      sequence: 10,
      occurred_at: new Date().toISOString(),
      payload: {},
    });

    // Process duplicate sequence 10
    (client as any).handleIncomingEvent({
      event_id: 'evt_10_dup',
      event_type: 'project.updated',
      aggregate_type: 'project',
      aggregate_id: 'proj_1',
      sequence: 10,
      occurred_at: new Date().toISOString(),
      payload: {},
    });

    // Process older sequence 5
    (client as any).handleIncomingEvent({
      event_id: 'evt_5',
      event_type: 'project.updated',
      aggregate_type: 'project',
      aggregate_id: 'proj_1',
      sequence: 5,
      occurred_at: new Date().toISOString(),
      payload: {},
    });

    // Process newer sequence 11
    (client as any).handleIncomingEvent({
      event_id: 'evt_11',
      event_type: 'project.updated',
      aggregate_type: 'project',
      aggregate_id: 'proj_1',
      sequence: 11,
      occurred_at: new Date().toISOString(),
      payload: {},
    });

    expect(received).toEqual([10, 11]);
  });

  it('disconnect() shuts down cleanly and resets state to DISCONNECTED', () => {
    const client = new RealtimeClient({ url: 'ws://localhost:8000/ws' });
    client.disconnect();
    expect(client.getState()).toBe('DISCONNECTED');
  });

  it('speaks the canonical subscription, control, heartbeat, and unsubscribe protocol', async () => {
    vi.useFakeTimers();
    const client = new RealtimeClient({
      url: 'ws://localhost:8000/ws',
      heartbeatIntervalMs: 50,
    });
    const received: EventEnvelope[] = [];
    const unsubscribe = client.subscribe(
      { aggregateType: 'run', aggregateId: 'run_123', afterSequence: 71 },
      (event) => received.push(event)
    );

    await client.connect();
    const socket = MockWebSocket.instances[0];
    socket.open();
    expect(JSON.parse(socket.sent[0])).toEqual({
      type: 'subscribe',
      aggregate_type: 'run',
      aggregate_id: 'run_123',
      after_sequence: 71,
    });

    socket.receive({ type: 'connected' });
    socket.receive({
      type: 'subscribed',
      aggregate_type: 'run',
      aggregate_id: 'run_123',
      cursor: 71,
    });
    socket.receive({ type: 'catchup_complete', cursor: 71 });
    socket.receive({
      event_id: 'evt_72',
      event_type: 'run.updated',
      aggregate_type: 'run',
      aggregate_id: 'run_123',
      sequence: 72,
      occurred_at: new Date().toISOString(),
      payload: { state: 'running' },
    });
    socket.receive({
      event_id: 'evt_72_duplicate',
      event_type: 'run.updated',
      aggregate_type: 'run',
      aggregate_id: 'run_123',
      sequence: 72,
      occurred_at: new Date().toISOString(),
      payload: { state: 'running' },
    });
    socket.receive({ type: 'pong' });
    expect(received.map((event) => event.sequence)).toEqual([72]);

    await vi.advanceTimersByTimeAsync(50);
    expect(JSON.parse(socket.sent.at(-1)!)).toMatchObject({ type: 'ping' });

    unsubscribe();
    expect(JSON.parse(socket.sent.at(-1)!)).toEqual({
      type: 'unsubscribe',
      aggregate_type: 'run',
      aggregate_id: 'run_123',
    });
    client.disconnect();
  });

  it('resubscribes after reconnect from the last processed sequence', async () => {
    vi.useFakeTimers();
    const client = new RealtimeClient({
      url: 'ws://localhost:8000/ws',
      reconnectBaseDelayMs: 10,
      reconnectMaxDelayMs: 10,
    });
    client.subscribe({ aggregateType: 'task', aggregateId: 'task_1' }, () => undefined);

    await client.connect();
    const first = MockWebSocket.instances[0];
    first.open();
    first.receive({
      event_id: 'evt_9',
      event_type: 'task.updated',
      aggregate_type: 'task',
      aggregate_id: 'task_1',
      sequence: 9,
      occurred_at: new Date().toISOString(),
      payload: {},
    });
    first.serverClose();

    await vi.advanceTimersByTimeAsync(10);
    const second = MockWebSocket.instances[1];
    expect(second).toBeDefined();
    second.open();
    expect(JSON.parse(second.sent[0])).toEqual({
      type: 'subscribe',
      aggregate_type: 'task',
      aggregate_id: 'task_1',
      after_sequence: 9,
    });
    client.disconnect();
  });
});
