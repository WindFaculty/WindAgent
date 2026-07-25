# Phase 3 risk register

## Risks carried forward
- 9 pre-existing test failures from Phase 2 baseline remain unfixed. Not introduced by Phase 3. Tracked for Phase 7 (composition roots) and Phase 11 (legacy backend cutover).
- `apps/backend` legacy event_bus still in use by old routers/sessions/websocket. Phase 11 territory.

## Risks introduced / mitigated
- Outbox schema change: added columns (aggregate_id, aggregate_type, schema_version, sequence_number, available_at, attempt_count, last_error, deduplication_key), renamed sequence -> sequence_number, retry_count -> attempt_count, dropped session_id column. No production data exists on V2 schema (greenfield), so no data migration needed. Phase 9 will formalize Alembic migrations.
- SQLite has no FOR UPDATE SKIP LOCKED. Mitigated with status-flip claim (pending -> publishing) using atomic UPDATE...WHERE status='pending'. Concurrent publishers cannot double-claim. On PostgreSQL, SKIP LOCKED applies.
- deduplication_key unique constraint is nullable-unique; NULLs allowed so legacy writes without dedup key do not conflict.
- API composition root instantiates OutboxEventPublisher with outbox_repo=None; actual publishing owned by Worker process (Phase 7 composition). API only writes to outbox via UnitOfWork.record_outbox_event. Publisher startup in API deferred to avoid split-brain publish.

## Verdict constraints
- Gate DURABLE_EVENT_PIPELINE_OPERATIONAL: PASS for storage+observability layer. Worker-side publisher loop wiring is Phase 7 scope.
