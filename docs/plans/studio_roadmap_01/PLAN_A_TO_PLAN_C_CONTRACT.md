# Plan A to Plan C Contract

Contract version: `studio.contract/v0.1`.

## A provides

- Application-facing ports/services for series, episodes, revisions, approvals, Studio runs, artifacts, events, idempotency, and capability status.
- Canonical commands/results/errors independent of FastAPI and TypeScript.
- Stable aggregate/version/hash concurrency semantics and an event cursor contract.
- Composition-provider functions that Plan C can inject into modular V3 routers without editing worker internals.
- Durable run status distinguishing queued, running, waiting-for-approval, retrying, completed, failed, and cancelled.

## C provides back

- `/api/v3/studio` HTTP mapping, validation/error/status-code mapping, authenticated actor propagation, idempotency headers, and expected-version handling.
- Schema/OpenAPI-driven client contracts and compatibility tests proving no TypeScript redefinition drift.
- Desktop run polling/event consumption and user workflows that call only the public application/API surface.
- A real-slice harness that drives the system from public API entry and reports task, artifact, approval, revision, lock, and recovery evidence.

## Invariants at the seam

1. V3 routers do not instantiate repositories, queues, provider clients, or orchestration engines.
2. Starting a run invokes the orchestrator service; the API cannot submit individual model tasks or mark work complete.
3. HTTP success is not used to imply durable completion. Long-running commands return a run resource and the desktop observes state/events.
4. Error payloads are redacted and stable; internal exception strings and provider credentials never cross the boundary.
5. V2 remains registered. Deprecation headers/documentation do not redirect or silently alter existing V2 behavior.
6. Capability-unavailable status is explicit and prevents the final slice from falling back to fake execution.

## Contract tests and handoff gate

- Domain/application error-to-HTTP mapping matrix passes.
- Replayed mutating requests have deterministic idempotency behavior.
- OpenAPI fixtures match A’s contract version and generated TypeScript types.
- Run polling survives API restart and reads durable state.
- `API_UI_INTEGRATION_GATE` requires a real API process and database-backed application services; fakes are restricted to unit/storybook fixtures and impossible in production composition.

Breaking changes require a version bump and coordinated fixture regeneration before implementation merges.
