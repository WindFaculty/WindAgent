# WindAgent V2 Worker

Job worker runtime delivered in Phase 7:

```text
PostgresJobQueue
  → atomic claim
  → LeaseGuard heartbeat/authority probe
  → JobHandlerRegistry dispatch
  → JobResultValidator
  → fencing-protected atomic result + outbox finalization
```

`WorkerModuleRuntime` receives jobs from `ModuleManifest` discovery, so a new
feature handler does not require an edit to the worker engine. `FakeJobHandler`
is foundation-only and exercises the `/debug/jobs` vertical slice.

Phase 10 attaches the persisted trace/correlation/causation/actor context to
each claimed job, creates fresh `run_id` and `task_id` values per execution,
and emits worker poll/job spans plus bounded outcome and duration metrics.
