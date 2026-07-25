# Phase 1 Risk Register — API Composition & Lifecycle Repair

## Summary of Resolved & Active Risks

The following table documents the status of risks addressed in Phase 1 and remaining active baseline risks.

| Risk ID | Defect Description | Status | Resolution / Remediation |
| :--- | :--- | :--- | :--- |
| **R-01** | `ApplicationContainer` lifespan accesses non-existent `container.orchestration_container` | **RESOLVED** | Removed invalid `orchestration_container` attribute from `app.state` in `lifespan.py`. |
| **R-02** | `PluginRegistry` and `SkillRegistry` missing `close()` async method | **RESOLVED** | Implemented `AsyncCloseablePort` (`async def close(self) -> None`) on `PluginRegistry`, `SkillRegistry`, `ToolRegistry`, and `WorkflowRegistry`. |
| **R-03** | `windagent_worker.composition` imports non-existent `windagent_intelligence.pipeline` | Active | To be resolved in Phase 2 (Package isolation & metadata). |
| **R-04** | `SqlOutboxRepository` instantiated with `session_factory` instead of `AsyncSession` | Active | To be resolved in Phase 5 (Outbox repository contract). |
| **R-05** | `OutboxEventPublisher` loop not started during container bootstrap | Active | To be resolved in Phase 6 (Outbox runtime). |
| **R-06** | `Migration 002` reads and writes to identical table names (`chat_sessions`, `execution_events`) | Active | To be resolved in Phase 7 / 8 (Data migration). |
| **R-07** | `HealthChecker` returns `NOT_REQUIRED` for missing outbox in production profile | Active | To be resolved in Phase 10 / 11 (Health wiring). |

---

## Governance Rules Enforced

1. **Clean Lifespan State**: `app.state` now only exposes container-owned dependencies.
2. **Canonical Shutdown Order**: Background tasks → Registries → Database connection.
3. **Idempotency**: Repeated calls to `bootstrap()` or `shutdown()` handle state transition safely without errors.
