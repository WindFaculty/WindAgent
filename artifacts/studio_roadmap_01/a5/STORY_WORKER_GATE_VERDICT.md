# STORY_WORKER_GATE — A5 verdict

- Contract: studio.contract/v0.1
- Gate: STORY_WORKER_GATE
- Verdict: **PASS**

## Checks

- PASS — handler_crosses_worker_path
- PASS — restart_recovery_reconciles
- PASS — envelope_validated_before_side_effects
- PASS — unregistered_task_type_rejected
- PASS — fake_runtime_rejected_in_certification
- PASS — fail_closed_leaves_no_artifacts
- PASS — worker_metrics_snapshot
- PASS — worker_test_suite_passes
- PASS — architecture_checker_green

## Scope

- StudioRuntimeAdapter decodes/validates the durable StudioTaskEnvelope BEFORE any side effect;
  unsupported schema/contract versions and unregistered frozen task types fail closed.
- Certification mode rejects fake runtimes and fixture model ports (no canned output can pass).
- Plan B handlers execute in the independent worker over the Studio UoW: input artifacts load
  by ref (frozen task IO map), output artifacts persist content-addressed and idempotent by hash,
  fenced by (worker, durable task id, fencing token) provenance.
- The generic TaskFinalizer commits task state + result + terminal event + outbox + lease release
  atomically; result_data IS the serialized StudioTaskResult, so generic tasks are untouched.
- Completion advances ONLY through the reconciler; crash windows are covered by lease expiry
  takeover (before provider/finalize) and StudioCompletionRecovery (after finalizer commit,
  before reconcile) — idempotent by design.
- Worker metrics (queue wait, execution, finalization, retry attempt, status) are redaction-safe:
  ids/durations only, never story content.

Evidence JSON: `artifacts/studio_roadmap_01/a5/evidence.json`
Generated: 2026-08-10T06:01:46.136685+00:00
