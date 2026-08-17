import { describe, it, expect, vi, beforeEach } from 'vitest';
import { RealtimeClient, createRealtimeClient } from '../realtimeClient';
import type { EventEnvelope } from '@windagent/api-contracts';

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
});
