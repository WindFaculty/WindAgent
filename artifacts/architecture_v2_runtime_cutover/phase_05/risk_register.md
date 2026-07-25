# Phase 5 Risk Register — Outbox Repository Contract & Transaction Semantics

## Summary of Resolved & Active Risks

The following table documents the status of risks addressed in Phase 5 and remaining active baseline risks.

| Risk ID | Defect Description | Status | Resolution / Remediation |
| :--- | :--- | :--- | :--- |
| **R-01** | `ApplicationContainer` lifespan accesses non-existent `container.orchestration_container` | **RESOLVED** | Resolved in Phase 1 (`lifespan.py`). |
| **R-02** | `PluginRegistry` and `SkillRegistry` missing `close()` async method | **RESOLVED** | Resolved in Phase 1 (`AsyncCloseablePort`). |
| **R-03** | `windagent_worker.composition` imports non-existent `windagent_intelligence.pipeline` | **RESOLVED** | Resolved in Phase 2 (`IntelligencePipeline`). |
| **R-08** | Architecture checker flags 32 dependency graph violations | **RESOLVED** | Resolved in Phase 2 (`scaffold_v2.yaml` policy & `pyproject.toml` sync). |
| **R-09** | Task submission and claiming relying on in-memory fallbacks | **RESOLVED** | Resolved in Phase 3 (`SqlDurableTaskQueue` and `SqlWorkSubmissionAdapter`). |
| **R-10** | Worker background process missing active heartbeat loop | **RESOLVED** | Resolved in Phase 4 (`ProductionWorker._heartbeat_loop()` and `SqlWorkerHeartbeatRepository`). |
| **R-11** | Stale worker execution continuing after fencing token takeover | **RESOLVED** | Resolved in Phase 4 (`record_heartbeat()` fencing validation + cancellation signal). |
| **R-04** | `SqlOutboxRepository` instantiated with `session_factory` instead of `AsyncSession` | **RESOLVED** | Resolved in Phase 5 (`SqlOutboxRepository` supports both `AsyncSession` and `async_sessionmaker`). |
| **R-05** | `OutboxEventPublisher` loop not started during container bootstrap | Active | To be resolved in Phase 6 (Outbox runtime). |
| **R-06** | `Migration 002` reads and writes to identical table names | Active | To be resolved in Phase 7 / 8 (Data migration). |
| **R-07** | `HealthChecker` returns `NOT_REQUIRED` for missing outbox in production profile | Active | To be resolved in Phase 10 / 11 (Health wiring). |

---

## Governance Rules Enforced

1. **Dual Mode Outbox Repository**: `SqlOutboxRepository` supports both `AsyncSession` (UOW mode) and `async_sessionmaker[AsyncSession]` (Publisher loop mode).
2. **Transactional Append**: Domain record and `OutboxRecordORM` append must occur in the exact same database transaction.
3. **Consistent Table Name**: Table name `v2_outbox_records` used consistently across ORM and storage repository layer.
