# ADR 0003: Single WebSocket Multiplexing and Durable Event Replay

## Status
Accepted

## Context
Currently, the system uses ephemeral in-memory WebSocket connections mapped 1-to-1 with agent sessions. Under this design, restarting the backend drops all events, slow consumers miss events if the queue fills up, and frontend clients cannot recover missing stream updates after temporary network disconnection. We need a reliable event streaming channel that supports replay and reconnect.

## Decision
We will redesign the event system to use a durable event store and a single multiplexed WebSocket channel.

### 1. Unified WebSocket URL
A single socket will be opened per conversation:
```
/ws/conversations/{conversation_id}?after_sequence={sequence_number}
```
All events for the conversation (and all its sub-agents) are multiplexed through this channel.

### 2. Envelope Specification
Every event has an envelope shape:
```json
{
  "event_id": "evt_uuid",
  "sequence": 1234,
  "conversation_id": "conv_uuid",
  "parent_task_id": "parent_task_uuid",
  "task_id": "task_uuid",
  "agent_instance_id": "agent_uuid",
  "run_id": "run_uuid",
  "correlation_id": "correlation_uuid",
  "event": "agent.output.delta",
  "timestamp": "ISO-8601-UTC-String",
  "data": {}
}
```

### 3. Persist-Before-Broadcast Invariant
To ensure data durability, the event publishing lifecycle follows this order strictly:
1. Generate the event object.
2. Insert the event into the database's durable event store.
3. Commit the database transaction.
4. Broadcast the event payload to active WebSocket connections.

No event is broadcasted without first being committed to the database.

### 4. Reconnect and Replay Logic
- The frontend client tracks the last received sequence number (`lastSequence`).
- Upon reconnection (using exponential backoff), the client requests events from `after_sequence = lastSequence`.
- The backend queries the database event store and replays all missed events in sequence order before resuming the real-time stream.
- The frontend event reducer must be idempotent based on `event_id` to prevent double-processing.

## Consequences
- **Zero Event Loss**: Temporary disconnects or slow connections no longer lead to lost terminal logs or agent updates.
- **Backend Restart Resilience**: Since events are stored in the database, restarting the backend allows the frontend to fully rebuild the state history from scratch.
- **Connection Efficiency**: Only one WebSocket connection is active per UI tab, reducing connection overhead.
