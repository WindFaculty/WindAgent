# Phase 3 Risk Register — Durable Task Submission & Atomic Claim

## Summary of Resolved & Active Risks

The following table documents the status of risks addressed in Phase 3 and remaining active baseline risks.

| Risk ID | Defect Description | Status | Resolution / Remediation |
| :--- | :--- | :--- | :--- |
| **R-01** | `ApplicationContainer` lifespan accesses non-existent `container.orchestration_container` | **RESOLVED** | Resolved in Phase 1 (`lifespan.py`). |
| **R-02** | `PluginRegistry` and `SkillRegistry` missing `close()` async method | **RESOLVED** | Resolved in Phase 1 (`AsyncCloseablePort`). |
| **R-03** | `windagent_worker.composition` imports non-existent `windagent_intelligence.pipeline` | **RESOLVED** | Resolved in Phase 2 (`IntelligencePipeline`). |
| **R-08** | Architecture checker flags 32 dependency graph violations | **RESOLVED** | Resolved in Phase 2 (`scaffold_v2.yaml` policy & `pyproject.toml` sync). |
| **R-09** | Task submission and claiming relying on in-memory fallbacks | **RESOLVED** | Resolved in Phase 3 (`SqlDurableTaskQueue` and `SqlWorkSubmissionAdapter`). |
| **R-04** | `SqlOutboxRepository` instantiated with `session_factory` instead of `AsyncSession` | Active | To be resolved in Phase 5 (Outbox repository contract). |
| **R-05** | `OutboxEventPublisher` loop not started during container bootstrap | Active | To be resolved in Phase 6 (Outbox runtime). |
| **R-06** | `Migration 002` reads and writes to identical table names | Active | To be resolved in Phase 7 / 8 (Data migration). |
| **R-07** | `HealthChecker` returns `NOT_REQUIRED` for missing outbox in production profile | Active | To be resolved in Phase 10 / 11 (Health wiring). |

---

## Governance Rules Enforced

1. **Transactional Task Submission**: Work submission writes `TaskRunORM` and `OutboxRecordORM` (`TaskSubmitted`) within a single SQL transaction.
2. **Atomic SQL Claiming**: Workers claim tasks using `SELECT ... FOR UPDATE` SQL queries, generating a new `fencing_token` and bumping `lease_generation` atomically.
3. **Fail-Closed Queue**: Production path never falls back to in-memory dictionaries.
