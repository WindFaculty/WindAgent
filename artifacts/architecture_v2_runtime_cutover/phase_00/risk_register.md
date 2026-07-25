# Phase 0 Risk Register — Baseline Lock & Defect Catalog

## Summary of Baseline Risks & Defect Inventory

The following table documents the baseline risks and defect impact inventory established at starting commit `5b26ed67e5550b97b86b83a21c836ff96bd049a6`.

| Risk ID | Defect Description | Severity | Impact Area | Remediation Phase |
| :--- | :--- | :--- | :--- | :--- |
| **R-01** | `ApplicationContainer` lifespan accesses non-existent `container.orchestration_container` | High | API Startup | Phase 1 |
| **R-02** | `PluginRegistry` and `SkillRegistry` missing `close()` async method | High | API Shutdown | Phase 1 |
| **R-03** | `windagent_worker.composition` imports non-existent `windagent_intelligence.pipeline` | Critical | Worker Process | Phase 2 |
| **R-04** | `SqlOutboxRepository` instantiated with `session_factory` instead of `AsyncSession` | Critical | Event Outbox | Phase 5 |
| **R-05** | `OutboxEventPublisher` loop not started during container bootstrap | High | Event Outbox | Phase 6 |
| **R-06** | `Migration 002` reads and writes to identical table names (`chat_sessions`, `execution_events`) | Critical | Data Migration | Phase 7 / 8 |
| **R-07** | `HealthChecker` returns `NOT_REQUIRED` for missing outbox in production profile | High | Observability | Phase 10 / 11 |
| **R-08** | Architecture checker flags 32 dependency graph violations | Medium | Architecture Governance | Phase 2 / 13 |
| **R-09** | Production worker relies on in-memory lease fallback rather than durable SQL queue claim | Critical | Worker Queue | Phase 3 / 4 |

## Governance Principles Enforced

1. **Zero Production Code Changes in Phase 0**: All existing files in `apps/`, `packages/`, `core/`, `storage/`, `observability/` remain untouched.
2. **Explicit Reproduction**: Each defect is verified via `tests/architecture/test_phase00_runtime_cutover_defects.py`.
3. **Fail-Closed Baseline**: No gate is marked `PASS` without empirical reproduction receipt.
