# Phase 2 Risk Register — Transactional Completion & Outbox Atomicity

| Risk ID | Description | Severity | Mitigation Strategy | Status |
|---|---|---|---|---|
| R2-01 | Fail-open worker logging warning on finalization error | High | Replaced with `FinalizeTaskExecution` within `SqlUnitOfWork`; exceptions fail closed and trigger full DB rollback. | Mitigated |
| R2-02 | Stale worker overwriting completed task | High | CAS update `WHERE id = :task_id AND version = :expected_version` rejects late worker results with `StaleResultRejectedError`. | Mitigated |
| R2-03 | Duplicate outbox publishing on worker crash retry | Medium | Outbox `deduplication_key` (`task_id:attempt:terminal_state:fencing_gen`) prevents duplicate outbox entries. | Mitigated |
