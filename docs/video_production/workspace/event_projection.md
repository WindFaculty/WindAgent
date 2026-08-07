# Realtime Event Projection Specification

## 1. Overview

Realtime updates are delivered via SSE (Server-Sent Events) or WebSocket connections (`/api/v2/events/stream`). UI clients use event projections to keep workspace state synchronized without polling.

## 2. Event Payload Schema

Every event emitted carries a global monotonic sequence cursor (`seq`):

```json
{
  "seq": 1042,
  "event_id": "evt_1042",
  "project_id": "vp_01",
  "event_type": "GENERATION_STARTED | CANDIDATE_PRODUCED | REVIEW_COMPLETED | COST_DEBITED | HUMAN_ACTION_REQUIRED | REVISION_MUTATED",
  "timestamp": "2026-08-02T13:30:00Z",
  "payload": {}
}
```

## 3. Disconnect, Reconnect & State Recovery

1. **Cursor Tracking**: The client persists `last_seen_seq` in local memory.
2. **Reconnection Protocol**: Upon connection loss, the client re-establishes SSE/WebSocket connection with header `Last-Event-ID: <last_seen_seq>` or query parameter `cursor=<last_seen_seq>`.
3. **Snapshot + Replay**: If the server event buffer has expired or sequence gap is detected, the server returns an HTTP `410 Gone` or `RESET` signal, prompting the client to re-fetch `GET /snapshot` followed by stream subscription from the snapshot sequence.
4. **Deduplication Guard**: The UI deduplicates events using `seq` or `event_id` to guarantee that stream reconnections NEVER trigger duplicate user notifications or duplicate automated actions.
5. **Health vs Connection Status**: Connection status (`CONNECTED | DISCONNECTED`) measures network link health ONLY. Workflow execution health (`HEALTHY | PAUSED | BLOCKED`) is determined strictly by server workflow state projections.
