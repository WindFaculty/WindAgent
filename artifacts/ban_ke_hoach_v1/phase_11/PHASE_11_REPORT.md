# Phase 11 Completion Report: Candidate → Experiment → Promotion

**Status**: COMPLETED & VERIFIED  
**Phase Reference**: `ban_ke_hoach_v1.md` §17, §24, §25, §27, §28, §29, §30, §35 (Candidate → Experiment → Promotion + Rollback)  
**Date**: 2026-08-29  
**Verdict**: PASS (0 boundary violations, 100% tests passing)

---

## 1. Executive Summary

Phase 11 establishes the **Empirical Experimentation, 7-Gate Promotion, and Post-Promotion Rollback Pipeline** in WindAgent. This phase marks the critical transition from mere reflection and candidate generation (Phase 9) and static harness versioning (Phase 10) to **true closed-loop self-improvement** validated by statistical evidence, safety regression gates, atomic harness commitments, and automated rollback upon regression.

The implementation strictly enforces core architectural invariants:
1. **7-Gate Promotion Criteria (§17, §35)**:
   - Minimum sample size reached (Local $\ge 2$, Project $\ge 3$, Global $\ge 5$).
   - Candidate beats or matches baseline performance without quality loss.
   - Zero safety regressions (`safety_score` $\ge$ baseline and $\ge 0.95$, 0 critical faults).
   - Zero reliability regressions (`reliability_score` $\ge$ baseline $- 0.05$ and $\ge 0.85$).
   - Cost delta within allocated budget limits.
   - Evidence provenance complete (valid supporting experience and evaluation IDs).
   - Evaluator uncertainty margin acceptable ($\le 0.45$).
2. **High-Risk Governance**: Global policies, executable skills, subagents, routing rules, and high/critical risk candidates strictly require human approval (`approved_by` must be a named human authority).
3. **Bounded Automated Promotion**: Low-risk project-scoped prompt rules can undergo automated promotion when all 7 gates pass.
4. **Post-Promotion Monitor & Rollback (§17, §35)**: Continuous production telemetry monitoring automatically triggers atomic rollback to the parent harness version and marks promotion decisions as `ROLLED_BACK` if errors, safety violations, or accuracy drops occur.
5. **Decoupled Architecture**: All layers interact via repository protocols in `core/windagent_core/contracts/repositories/`, maintaining 0 boundary violations under V3 architecture policy.

---

## 2. Implemented Capabilities

### A. Core Domain Layer (`core/windagent_core/domain/` & `contracts/`)
- **Experiment Domain (`experiment.py`)**:
  - `ExperimentStatus`: `DRAFT`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`.
  - `ExperimentVerdict`: `BEATS_BASELINE`, `TIE`, `INFERIOR`, `INCONCLUSIVE`, `UNSAFE`.
  - `ExperimentType`: `REPLAY`, `BENCHMARK`, `A_B_SHADOW`, `LIVE_TEST`.
  - `ExperimentMetrics`: accuracy, safety_score, reliability_score, latency_ms, cost_usd, sample_size, error_count, custom_metrics.
  - `StatisticalComparison`: accuracy_delta, safety_delta, reliability_delta, cost_delta, latency_delta_ms, p_value, 95% CI, uncertainty_margin, is_statistically_significant.
  - `compute_statistical_comparison()`: Pure domain helper for two-sample z-tests and metric comparisons.
  - `Experiment`: Immutable domain entity with lifecycle transition methods (`start()`, `complete()`, `fail()`, `cancel()`).
- **Promotion Domain (`promotion.py`)**:
  - `PromotionStatus`: `PENDING_APPROVAL`, `PROMOTED`, `REJECTED`, `ROLLED_BACK`.
  - `GateCheckResult`: 7-gate validation record with failure attribution.
  - `PostPromotionHealth`: Telemetry aggregation and regression detection model.
  - `PromotionDecision`: Immutable domain entity tracking approval signatures, rationale, and rollback states.
- **Repository Protocols (`contracts/repositories/`)**:
  - `HarnessRepositoryProtocol` (`harness_repository.py`)
  - `ExperimentRepositoryProtocol` (`experiment_repository.py`)
  - `PromotionRepositoryProtocol` (`promotion_repository.py`)

### B. Evals & Intelligence Layer (`evals/` & `intelligence/`)
- **CandidateComparisonEngine (`evals/windagent_evals/candidate_comparison.py`)**:
  - Evaluates benchmark episode batches, computing statistical significance and safety gates.
- **HarnessService Decoupling (`intelligence/windagent_intelligence/harness/harness_service.py`)**:
  - Decoupled from concrete storage, now depending on `HarnessRepositoryProtocol`.

### C. Orchestration Layer (`orchestration/windagent_orchestration/learning/`)
- **PromotionGate (`promotion_gate.py`)**:
  - Evaluates all 7 gates and determines high-risk vs low-risk classification.
- **ExperimentRunner (`experiment_runner.py`)**:
  - Coordinates candidate vs baseline experiments on replay/benchmark datasets.
- **RollbackCoordinator (`rollback_coordinator.py`)**:
  - Monitors post-promotion telemetry for error spikes, safety faults, or performance drops, triggering atomic rollback to parent `HarnessVersion`.
- **LearningWorkflowService (`learning_workflow_service.py`)**:
  - High-level coordinator for Candidate $\to$ Experiment $\to$ Promotion $\to$ Commit $\to$ Monitor $\to$ Rollback.

### D. Storage Layer (`storage/windagent_storage/`)
- **Alembic Migration 0028 (`0028_experiment_promotion.py`)**:
  - Creates `experiments` and `promotion_decisions` tables with compound indexes.
- **ORM Models (`orm/experiment_models.py`, `orm/promotion_models.py`)**:
  - `ExperimentORM` and `PromotionDecisionORM` mapped to `BaseORM.metadata`.
- **Repositories (`repositories/experiment_repository.py`, `repositories/promotion_repository.py`)**:
  - Async SQL persistence, JSON serialization, and filtered queries.

### E. API Layer (`apps/api/windagent_api/routers/`)
- **v2_experiments.py**:
  - `POST /api/v2/experiments`: Create & run experiment.
  - `GET /api/v2/experiments`: List experiments.
  - `GET /api/v2/experiments/{experiment_id}`: Retrieve experiment details.
- **v2_promotions.py**:
  - `POST /api/v2/promotions/evaluate`: Evaluate 7-gate promotion criteria.
  - `POST /api/v2/promotions/promote`: Execute promotion and create new `HarnessVersion`.
  - `POST /api/v2/promotions/rollback`: Execute rollback to parent `HarnessVersion`.
  - `GET /api/v2/promotions`: List promotion decisions.
  - `GET /api/v2/promotions/{decision_id}`: Get decision details.

---

## 3. Verification Evidence

### Test Execution Results
1. **Phase 11 Component Suite** (`tests/component/orchestration/test_phase11_experiment_promotion.py`):
   - `test_experiment_domain_immutability_and_lifecycle`: **PASSED**
   - `test_promotion_decision_domain_immutability`: **PASSED**
   - `test_candidate_comparison_statistical_engine`: **PASSED**
   - `test_7_gate_promotion_criteria_enforcement`: **PASSED**
   - `test_high_risk_mutation_requires_human_approval`: **PASSED**
   - `test_bounded_automated_promotion_for_low_risk_prompt_rule`: **PASSED**
   - `test_atomic_harness_version_commitment_on_promotion`: **PASSED**
   - `test_post_promotion_regression_detection_and_rollback`: **PASSED**
   - `test_experiment_and_promotion_repositories_async_sql`: **PASSED**
   - `test_fastapi_v2_experiments_endpoints`: **PASSED**
   - `test_fastapi_v2_promotions_endpoints`: **PASSED**
   - `test_migration_0028_schema_and_indexes_integrity`: **PASSED**
   - *Result*: **12 / 12 PASSED (100%)**

2. **Combined Multi-Phase Learning Suite** (Phases 8, 9, 10, 11):
   - *Result*: **47 / 47 PASSED (100%)**

3. **Storage Migrations Suite** (`tests/component/migrations/`):
   - *Result*: **99 / 99 PASSED, 4 SKIPPED (100%)**

4. **Architecture Invariants V3** (`scripts/check_architecture_v3.py`):
   - *Result*: **PASS (0 violations, 18 packages, 60 dependency edges)**

5. **Code Quality** (`ruff check`):
   - *Result*: **PASS (0 lint errors)**

