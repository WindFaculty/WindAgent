# Phase 10 — Observability foundation

Date: 2026-09-02

## Scope delivered

| Signal / context | Implementation |
| ---------------- | -------------- |
| Trace context | W3C `traceparent`, `OperationContext`, task-local binding |
| Causal IDs | trace, correlation, causation, actor on HTTP/commands/queries |
| Job IDs | persisted job trace/actor plus generated job/run/task span fields |
| Structured logs | deterministic JSON formatter and recursive secret redaction |
| Metrics | bounded registry, counters/histogram summaries, `/metrics` |
| Tracing | vendor-neutral runtime spans for HTTP, buses, poll, and job execution |
| Audit events | trace/correlation/causation attached to security audit records |
| Health/readiness | existing `/health` and PostgreSQL-backed `/ready` retained |

No OpenTelemetry, Prometheus client, or logging vendor type enters the kernel,
platform contracts, or feature-module boundary. `Telemetry` and
`MetricsExporter` remain replaceable ports.

## Propagation path

```text
HTTP traceparent + correlation/causation headers
        ↓
RequestContextMiddleware (new local span + response headers)
        ↓
AuthenticationMiddleware (verified actor binding)
        ↓
CommandBus / QueryBus spans
        ↓
JobSubmission (trace + actor + correlation + causation)
        ↓
platform_jobs (Alembic 0004)
        ↓
WorkerRuntime (job_id + fresh run_id + task_id)
        ↓
handler / atomic finalization / outbox publication
```

Metrics use only stable labels (`method`, route template, status class,
message kind, job type, outcome). Trace, actor, correlation, job, run, and
task IDs are log/span attributes, never metric labels.

## Gates

Current local evidence:

```text
phase 0 manifest validator  PASS
Ruff                        PASS
mypy strict                 PASS (174 source files)
full pytest                 PASS (281 passed, including PostgreSQL)
frontend typecheck/test/build PASS
```

New coverage includes W3C parse/rejection/continuation, task-local context
restoration, trace/correlation response headers, metrics aggregation and
series bounds, Prometheus rendering, JSON redaction, HTTP and bus spans,
durable job trace/actor round-trip, worker job/run/task context, contextual
security audit, and the `0001 → 0004` migration round-trip.

Phase 10 completes Milestone 1. Business-module migration may now start with
Phase 11 (Model Gateway), subject to the normal per-module design/parity/
integration gates.
