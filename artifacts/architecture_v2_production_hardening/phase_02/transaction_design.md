# Phase 2 Transaction Design — Transactional Worker Completion and Outbox Atomicity

## Overview

Worker execution finalization guarantees that task completion, CAS state updates, result persistence, artifact references, terminal event recording, outbox publishing, and lease release are executed within a single atomic database transaction (`FinalizeTaskExecution`).

## Atomic Execution Flow

```text
+-------------------------------------------------------------------------------+
|                      Single Database Transaction                              |
|                                                                               |
|  1. Idempotency Check  --> If outbox record exists, return ALREADY_FINALIZED  |
|  2. Lease Validation   --> Validate lease & fencing_token match              |
|  3. Conditional CAS    --> UPDATE task_runs SET state='completed', version=v+1|
|                            WHERE id=? AND version=expected_version            |
|  4. Persist Result     --> Insert task_execution_results_v2 row               |
|  5. Terminal Event     --> Insert event into EventStore                       |
|  6. Transaction Outbox --> Insert record into Outbox with deduplication_key   |
|  7. Release Lease      --> UPDATE execution_leases SET status='completed'     |
|  8. Commit             --> ATOMIC COMMIT OR ROLLBACK                          |
+-------------------------------------------------------------------------------+
```

## Failure Semantics

If any step (1–7) raises an exception, the Unit of Work transaction triggers a full database rollback.
- Task remains in its previous state (`running`).
- Outbox receives zero partial writes.
- Lease remains active (not released fail-open).
- Worker raises a retryable persistence error, allowing recovery leader or worker takeover.
