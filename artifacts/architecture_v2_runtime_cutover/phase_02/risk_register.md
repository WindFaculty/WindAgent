# Phase 2 Risk Register — Package Metadata & Isolation Proof

## Summary of Resolved & Active Risks

The following table documents the status of risks addressed in Phase 2 and remaining active baseline risks.

| Risk ID | Defect Description | Status | Resolution / Remediation |
| :--- | :--- | :--- | :--- |
| **R-01** | `ApplicationContainer` lifespan accesses non-existent `container.orchestration_container` | **RESOLVED** | Resolved in Phase 1 (`lifespan.py`). |
| **R-02** | `PluginRegistry` and `SkillRegistry` missing `close()` async method | **RESOLVED** | Resolved in Phase 1 (`AsyncCloseablePort`). |
| **R-03** | `windagent_worker.composition` imports non-existent `windagent_intelligence.pipeline` | **RESOLVED** | Created `IntelligencePipeline` facade in `intelligence/windagent_intelligence/pipeline.py` and exported in `__init__.py`. |
| **R-08** | Architecture checker flags 32 dependency graph violations | **RESOLVED** | Updated workspace `pyproject.toml` manifests (`api`, `worker`, `cli`) and synchronized `scaffold_v2.yaml` policy (0 violations). |
| **R-04** | `SqlOutboxRepository` instantiated with `session_factory` instead of `AsyncSession` | Active | To be resolved in Phase 5 (Outbox repository contract). |
| **R-05** | `OutboxEventPublisher` loop not started during container bootstrap | Active | To be resolved in Phase 6 (Outbox runtime). |
| **R-06** | `Migration 002` reads and writes to identical table names (`chat_sessions`, `execution_events`) | Active | To be resolved in Phase 7 / 8 (Data migration). |
| **R-07** | `HealthChecker` returns `NOT_REQUIRED` for missing outbox in production profile | Active | To be resolved in Phase 10 / 11 (Health wiring). |

---

## Governance Rules Enforced

1. **Explicit Package Dependencies**: Every workspace package imported by `apps/api` or `apps/worker` or `apps/cli` must be declared in `pyproject.toml`.
2. **Clean Virtual Environment Isolation**: Proven via `scripts/test_api_isolation.ps1` and `scripts/test_worker_isolation.ps1`.
3. **Zero Policy Drift**: `scripts/check_architecture_imports.py` verified 0 violations.
