# DURABLE_ORCHESTRATION_GATE — A4 verdict

- Contract: studio.contract/v0.1
- Gate: DURABLE_ORCHESTRATION_GATE
- Verdict: **PASS**
- Migration: 0011_studio_run_nodes (sha256 9442f1e9bb6dfe95...)
- Current head: ['0011_studio_run_nodes']

## Checks

- PASS — fresh_upgrade_reaches_0011
- PASS — dag_task_correlation_persisted
- PASS — root_dispatched_with_committed_identity
- PASS — completion_advanced_only_through_reconciliation
- PASS — orchestration_test_suite_passes
- PASS — architecture_checker_green

## Scope

- OrchestratorService extension seam routes Studio runs through the sole Story authority.
- Deterministic DAG builder over frozen task types/checkpoints; run + node state persist BEFORE submission.
- StudioTaskSubmissionPort adapter wraps the durable queue (task_runs + outbox, atomic) with
  namespaced idempotency keys; nodes are marked DISPATCHED only with the committed task identity.
- StudioCompletionReconciler is the ONLY DAG-advancing path: stale/duplicate/out-of-order completions
  are rejected or no-op'd; bounded retry re-dispatches with a fresh (run, node, attempt) key.
- Approval waits are durable run state (WAITING_APPROVAL); APPROVED resumes through the orchestrator,
  REJECTED fails the run. Cancellation is idempotent; terminal history is never rewritten.
- Restart/resume: submitted-but-unmarked work is found by idempotency; dispatched-without-task nodes
  are re-submitted on resume; terminal runs reject all later completions.

Evidence JSON: `artifacts/studio_roadmap_01/a4/evidence.json`
Generated: 2026-08-10T04:54:35.755758+00:00
