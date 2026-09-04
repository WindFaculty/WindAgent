# ADR-0003: Outbox carries causal identity end-to-end

- Status: Accepted
- Date: 2026-09-02
- Phase: 6 (events + outbox)

## Context

Plan section 10 defines the envelope with `actor_id`, `correlation_id` and
`causation_id`, and section 30 requires intentional behavior changes to be
documented. The old transactional outbox did **not** persist these fields:
its `OutboxRecordORM` stopped at payload/status/claim columns, so the
publisher reconstructed envelopes without any causal context. Consumers
downstream of delivery could not correlate an event back to the operation
that caused it, and Phase 10 (observability) would have had a permanent
gap at exactly the boundary the outbox owns.

## Decision

- `platform_outbox` stores `actor_id`, `correlation_id`, `causation_id`
  alongside the event fields (nullable, 36-char UUID strings, same as the
  event store).
- `TransactionalOutbox.record` writes them from the envelope;
  `OutboxRecord.to_envelope` restores them on delivery.
- The delivery-time envelope therefore equals the recorded envelope in
  identity, causality, and payload — a parity *improvement* over the old
  system, applied at the only seam where the old behavior lost data.

## Consequences

- Phase 7 worker finalization and Phase 10 tracing can thread
  `correlation_id`/`causation_id` from a job submission through every
  published event without re-deriving context.
- Outbox rows grow by 3 nullable columns (~108 bytes worst case) —
  negligible against delivery guarantees.
- Any future event-store replay (realtime reconnect, Phase 8+) reads the
  same columns from `platform_events`, which already had them.
