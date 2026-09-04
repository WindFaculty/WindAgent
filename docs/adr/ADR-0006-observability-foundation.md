# ADR-0006: Observability foundation — W3C context, bounded metrics, JSON logs

- Status: Accepted
- Date: 2026-09-02
- Phase: 10 (observability foundation)

## Context

Plan section 14 requires every operation to carry trace, correlation,
causation, and actor identity; job execution additionally needs job, run,
and task identity. Structured logs, metrics, tracing, audit events, health,
and readiness must exist before the first business module migrates.

The Phase 3 `Telemetry` protocol was intentionally vendor-neutral. Phase 10
must make that contract operational without allowing a vendor SDK to become
a platform or module dependency.

## Decisions

1. **W3C Trace Context is the HTTP propagation format.** The API accepts a
   valid `traceparent`, continues its trace with a fresh local span, and
   returns `traceparent`, `X-Trace-Id`, `X-Correlation-Id`, and
   `X-Request-Id`. Malformed external values are ignored and replaced.
2. **Causal context is task-local.** `OperationContext` uses `contextvars`,
   so async work inherits the active trace/correlation/causation/actor
   fields without global mutable state. Verified authentication rebinds the
   downstream context with its `actor_id`.
3. **Durable jobs carry trace and actor identity.** Alembic revision `0004`
   adds nullable `trace_id` and `actor_id` columns to `platform_jobs`.
   Correlation and causation continue using the Phase 7 columns. Every
   claimed execution creates fresh `run_id` and `task_id` values and emits
   worker spans/metrics with stable job type and outcome labels.
4. **Metrics are bounded and low-cardinality.** `MetricRegistry` limits the
   total series and labels per series. IDs never become metric labels.
   The API exposes Prometheus text at `/metrics`; another implementation can
   replace the `Telemetry`/`MetricsExporter` ports.
5. **Logs are single-line JSON and redact structured secrets.** Known secret
   keys (authorization, cookie, password, secret, token, API key, private
   key) are recursively replaced with `[REDACTED]`. Logs/spans attach the
   active causal IDs automatically and never record HTTP/job payloads.
6. **Audit uses the same context.** Security audit records now include trace,
   correlation, and causation identity; the outbox event preserves actor,
   correlation, and causation as canonical event-envelope fields.
7. **Health/readiness remain separate from metrics.** `/health` is liveness,
   `/ready` verifies configuration and PostgreSQL, and `/metrics` is a
   scrape surface. All remain public infrastructure probes when bearer
   authentication is enabled.

## Consequences

- HTTP, command/query dispatch, durable jobs, worker execution, and policy
  audit can be followed through a single causal chain.
- The default runtime is useful without an external collector: JSON logs,
  retained bounded span/event records, and scrapeable process metrics work
  immediately.
- Process-local metrics are not a durable analytics store. Production may
  add an OpenTelemetry/Prometheus exporter behind the existing ports without
  changing kernel, platform contracts, modules, routes, or worker logic.
- Free-form exception messages are not exported as span attributes; only
  exception type is recorded. Durable job error behavior remains unchanged.
