# Phase 2 risk register

- Existing production readiness still contains unrelated hardcoded schema/outbox/event checks. Deferred to Phase 10.
- Worker heartbeat adapter exists; worker process heartbeat wiring remains limited to future durable worker composition work. API never accesses Worker object.
- API development profile returns `DEGRADED` without worker; production returns HTTP 503.
