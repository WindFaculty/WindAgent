# Phase 18: Quality, Evaluations, Verification & Regression

**Status**: COMPLETED  
**Date**: 2026-09-02  
**Module**: `windagent.modules.quality`  
**Milestone**: Milestone 3 (WindAgent Product)

---

## 1. Executive Summary

Phase 18 implements the complete Quality & Evaluation subsystem for WindAgent V2. It incorporates all 11 canonical evaluation dimensions, a fail-closed execution evidence model, 9 automated rubric evaluators/graders, 7 verification gate types, baseline comparison regression detection, and markdown quality certification report generation.

---

## 2. Capabilities & Architecture

### Domain Layer (`windagent.modules.quality.domain`)
- **11 Evaluation Dimensions**: `TASK_SUCCESS`, `ARTIFACT_QUALITY`, `TOOL_CORRECTNESS`, `SAFETY`, `COST`, `LATENCY`, `RELIABILITY`, `MODEL_ROUTING`, `CONTEXT_EFFICIENCY`, `DELEGATION_EFFICIENCY`, `REGRESSION`.
- **Fail-Closed Evidence Rule**: `EvaluationRecord` mandates evidence refs. Empty evidence or blocked status strictly forces `score = 0.0` and `passed = False`.
- **Aggregate**: `EvaluationRunAggregate` managing lifecycle (`PENDING` -> `RUNNING` -> `COMPLETED` / `FAILED` / `BLOCKED`), calculating composite scores with weights.
- **Graders (`graders.py`)**:
  - `ExactMatchGrader`: Literal and normalized equality.
  - `RegexGrader`: Pattern matching.
  - `NumericThresholdGrader`: Min/max bounds.
  - `JsonSchemaGrader`: Schema compliance and required key verification.
  - `CostLimitGrader`: USD / token limit validation.
  - `LatencyGrader`: Millisecond SLA validation.
  - `SafetyRuleGrader`: Secret leakage, prompt injection, and forbidden content checks.
  - `CodeCorrectnessGrader`: Syntax, test pass, and compilation checks.
  - `CompositeRubricGrader`: Multi-criterion weighted rubric evaluation.
- **Verification Gates (`verification.py`)**:
  - 7 Gate Types: `TEST_RUNNER`, `LINTER`, `TYPE_CHECKER`, `POLICY_ENGINE`, `SECURITY_SCAN`, `SANDBOX_CHECK`, `INTEGRITY`.
  - `ExecutionEvidence` recording command exit code, stdout/stderr, execution logs.
  - `VerificationSuiteReport` evaluating pass/fail/block status with blocker reasons.
- **Regression Detection (`regression.py`)**:
  - `MetricDelta` calculating performance deltas against candidate/baseline versions.
  - `BaselineComparison` detecting regressions when `delta < -regression_threshold`.
- **Quality Reports (`reports.py`)**:
  - `QualityReportGenerator` formatting structured scorecard payloads and generating verifiable Markdown Quality Certificates.

### Application Layer (`windagent.modules.quality.application`)
- **Commands**: 8 command contracts (`CreateEvaluationDataset`, `AddDatasetTestCase`, `StartEvaluationRun`, `RecordEvaluationMetric`, `FinalizeEvaluationRun`, `ExecuteDatasetEvaluation`, `RunVerificationSuite`, `CompareBaseline`).
- **Queries**: 8 query contracts (`GetEvaluationDataset`, `ListEvaluationDatasets`, `GetEvaluationRun`, `ListEvaluationRuns`, `GetVerificationReport`, `ListVerificationReports`, `GetBaselineComparison`, `ListBaselineComparisons`, `GetQualitySummary`, `GetQualityCertificationMarkdown`).
- **Events**: Outbox events (`quality.eval.started`, `quality.eval.completed`, `quality.verification.completed`, `quality.regression.detected`).

### Infrastructure Layer (`windagent.modules.quality.infrastructure`)
- **Storage**: `SqlQualityStore` (SQLAlchemy async) and `InMemoryQualityStore`.
- **Database Tables**:
  - `quality_datasets`: Curated benchmark test datasets.
  - `quality_test_cases`: Individual test case inputs, expected outputs, rubrics.
  - `quality_evaluation_runs`: Run execution status and aggregate scores.
  - `quality_evaluation_records`: Detailed metric evaluations with evidence refs.
  - `quality_verification_reports`: Verification suite gate checks and execution evidence.
  - `quality_baseline_comparisons`: Candidate vs baseline comparison metrics and regression flags.
- **Migration**: `migrations/versions/0013_quality.py`.

### Background Jobs (`windagent.modules.quality.jobs`)
- `quality.eval.execute`: Executes dataset evaluations asynchronously across agent runners.
- `quality.verification.run`: Runs verification suites against candidate builds/artifacts.
- `quality.benchmark.run`: Schedules automated benchmark suites.
- `quality.regression.detect`: Detects statistical drift and regressions against golden baselines.

### API Layer (`windagent.modules.quality.api`)
- REST routes mounted at `/api/v4/quality`:
  - `POST /api/v4/quality/datasets`
  - `GET /api/v4/quality/datasets`
  - `GET /api/v4/quality/datasets/{dataset_id}`
  - `POST /api/v4/quality/datasets/{dataset_id}/cases`
  - `POST /api/v4/quality/evaluations/runs`
  - `GET /api/v4/quality/evaluations/runs`
  - `GET /api/v4/quality/evaluations/runs/{run_id}`
  - `POST /api/v4/quality/evaluations/runs/{run_id}/metrics`
  - `POST /api/v4/quality/evaluations/runs/{run_id}/finalize`
  - `POST /api/v4/quality/evaluations/execute-dataset`
  - `POST /api/v4/quality/verification/suites/run`
  - `GET /api/v4/quality/verification/reports`
  - `GET /api/v4/quality/verification/reports/{report_id}`
  - `POST /api/v4/quality/baselines/compare`
  - `GET /api/v4/quality/baselines/comparisons`
  - `GET /api/v4/quality/baselines/comparisons/{comparison_id}`
  - `GET /api/v4/quality/summary`
  - `GET /api/v4/quality/evaluations/runs/{run_id}/certificate`

---

## 3. Verification & Parity

- **Unit Tests**:
  - `tests/unit/test_quality_domain.py`: Fail-closed evidence rule, aggregate lifecycle, verification gates, baseline regression, markdown certificate generation.
  - `tests/unit/test_quality_graders.py`: All 9 evaluators (exact match, regex, numeric, json schema, cost, latency, safety, code correctness, composite rubric).
  - `tests/unit/test_quality_services.py`: Service orchestration, dataset management, verification suite execution, baseline comparison.
  - `tests/unit/test_quality_api.py`: Manifest discovery, REST dataset/run/metric/finalize flow.
- **Parity Tests**:
  - `tests/parity/test_quality_parity.py`: Verifying behavioral parity with legacy evals (11 dimensions, fail-closed rule, regression formula).
