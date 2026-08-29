# Phase 9 Completion Report: Diagnosis & Candidate Learning

**Status**: COMPLETED & VERIFIED  
**Phase Reference**: `ban_ke_hoach_v1.md` §14, §23, §24, §25, §27 (Diagnosis & Candidate Learning)  
**Date**: 2026-08-29  
**Verdict**: PASS (0 boundary violations, 100% tests passing)

---

## 1. Executive Summary

Phase 9 implements the **Diagnosis & Candidate Learning Engine** as specified in `ban_ke_hoach_v1.md` §14, §23, and §24. Building upon Phase 8's empirical `Experience` repository and Phase 7's multi-dimensional evaluations, Phase 9 bridges observational telemetry and versioned harness refinement (Phase 10 Continual Harness & Phase 11 Promotion Gate).

The implementation strictly enforces core architectural invariants:
1. **Non-Self-Promoting Invariant**: Diagnostic models and algorithms generate `LearningCandidate` instances in the `PROPOSED` state. They are strictly prohibited from directly modifying system prompts, active harness versions, or policies.
2. **Hard Rule (§14)**: `1 failure -> reflection -> candidate (PROPOSED with sample_size=1)`. Single failure observations can never directly rewrite prompts or pass eligibility gates without meeting statistical sample size thresholds.
3. **Domain Distinction**: `Experience != MemoryFact != LearningCandidate != LearnedRule != Skill != Policy`.

---

## 2. Implemented Capabilities

### A. Core Domain Layer (`core/windagent_core/domain/candidate.py`)
- **Lifecycle Enums**:
  - `CandidateKind`: `PROMPT_RULE` (`"prompt_rule"`), `MEMORY` (`"memory"`), `SKILL` (`"skill"`), `SUBAGENT_SPEC` (`"subagent_spec"`), `ROUTING_POLICY` (`"routing_policy"`).
  - `CandidateStatus`: `PROPOSED` (`"proposed"`), `ELIGIBLE` (`"eligible"`), `EXPERIMENTING` (`"experimenting"`), `PROMOTED` (`"promoted"`), `REJECTED` (`"rejected"`), `EXPIRED` (`"expired"`).
  - `CandidateRiskLevel`: `LOW` (`"low"`), `MEDIUM` (`"medium"`), `HIGH` (`"high"`), `CRITICAL` (`"critical"`).
  - `CandidateScope`: `LOCAL` (`"local"`), `PROJECT` (`"project"`), `GLOBAL` (`"global"`).
  - `LearnedRuleState`: `CANDIDATE` (`"candidate"`), `EXPERIMENTING` (`"experimenting"`), `PROMOTED` (`"promoted"`), `DEPRECATED` (`"deprecated"`), `ROLLED_BACK` (`"rolled_back"`).
- **LearningCandidate Entity (Immutable)**:
  - Fields: `candidate_id`, `kind`, `condition`, `proposed_change`, `reasoning_summary`, `supporting_experiences`, `counter_evidence`, `sample_size`, `confidence`, `scope`, `risk_level`, `status`, `project_id`, `domain`, `metadata`, `created_at`, `updated_at`.
  - Methods: `mark_eligible()`, `start_experiment()`, `reject()`, `expire()`, `with_evidence()`, `with_counter_evidence()`, `assert_candidate_invariants()`.
- **LearnedRule Entity (Immutable)**:
  - Tracks structured rule condition, recommendation, domain attribution, evidence references, confidence, version, and lifecycle state.
  - Methods: `deprecate()`, `rollback()`.

### B. Intelligence Layer (`intelligence/windagent_intelligence/candidate/`)
- **CandidateGenerator (`candidate_generator.py`)**:
  - `generate_from_single_experience()`: Converts a single diagnosed experience into a `PROPOSED` candidate (`sample_size=1`).
  - `mine_candidates_from_experiences()`: Clusters diagnosed experiences by YouTube hook retention / packaging attribution (§22), recurring tool failure anomalies, and general domain patterns. Computes composite confidence and counter-evidence penalties.
- **EligibilityGate (`eligibility_gate.py`)**:
  - Validates qualification criteria:
    - Scope-based sample size thresholds (`LOCAL=2`, `PROJECT=3`, `GLOBAL=5`).
    - Confidence threshold (`>= 0.65` for low/medium risk, `>= 0.80` for high/critical risk).
    - Counter-evidence ratio tolerance (`<= 0.35`).
    - Zero-tolerance safety invariant enforcement.
- **CandidateService (`service.py`)**:
  - Orchestrates candidate generation, mining, eligibility evaluation, and state transitions.

### C. Storage Layer (`storage/windagent_storage/`)
- **Alembic Migration 0026** (`0026_candidate_learning.py`):
  - Creates `learning_candidates` and `learned_rules` tables with compound indexes (`ix_candidate_status_conf`, `ix_candidate_proj_status`, `ix_candidate_domain_status`, `ix_candidate_kind_status`, `ix_rule_domain_state`).
- **ORM Models** (`storage/windagent_storage/orm/candidate_models.py`):
  - `LearningCandidateORM` and `LearnedRuleORM` mapped cleanly to canonical `BaseORM.metadata`.
- **CandidateRepository** (`storage/windagent_storage/repositories/candidate_repository.py`):
  - Async SQL persistence, batch saving, status and project querying, state updates, and learned rule CRUD.

### D. API Layer (`apps/api/windagent_api/routers/v2_candidates.py`)
- Endpoints:
  - `POST /api/v2/candidates`: Propose learning candidate.
  - `POST /api/v2/candidates/mine`: Mine clustered candidates from experience payloads.
  - `GET /api/v2/candidates`: List candidates with multi-criteria filtering.
  - `GET /api/v2/candidates/{candidate_id}`: Retrieve candidate details.
  - `POST /api/v2/candidates/{candidate_id}/evaluate`: Evaluate eligibility against thresholds.
  - `POST /api/v2/candidates/{candidate_id}/mark-eligible`: Transition candidate to `ELIGIBLE`.
  - `POST /api/v2/candidates/{candidate_id}/reject`: Transition candidate to `REJECTED`.
  - `POST /api/v2/candidates/{candidate_id}/expire`: Transition candidate to `EXPIRED`.
  - `GET /api/v2/candidates/rules`: List learned rules.

---

## 3. Verification Evidence

### Test Execution Results
1. **Phase 9 Component Tests** (`tests/component/intelligence/test_phase9_candidate_learning.py`):
   - `test_candidate_states_and_immutability`: **PASSED**
   - `test_hard_rule_single_failure_reflection`: **PASSED**
   - `test_candidate_state_transitions`: **PASSED**
   - `test_candidate_evidence_and_counter_evidence`: **PASSED**
   - `test_candidate_miner_youtube_hook_attribution`: **PASSED**
   - `test_candidate_miner_tool_failure_anomalies`: **PASSED**
   - `test_eligibility_gate_scope_and_risk_thresholds`: **PASSED**
   - `test_learned_rule_lifecycle_and_rollback`: **PASSED**
   - `test_candidate_service_coordination`: **PASSED**
   - `test_candidate_repository_sql_crud`: **PASSED**
   - `test_api_v2_candidates_endpoints`: **PASSED**
   - `test_candidate_tables_metadata_integrity`: **PASSED**
   - *Result*: **12 / 12 PASSED (100%)**

2. **Combined Component Regression Suite** (Phases 6, 7, 8, 9):
   - *Result*: **106 / 106 PASSED (100%)**

3. **Storage Migration Suite** (`tests/component/migrations/`):
   - *Result*: **99 / 99 PASSED, 1 SKIPPED (100%)**

4. **Architecture Invariants V3**:
   - `scripts/check_architecture_v3.py`: **PASS (0 violations)**

5. **Code Quality**:
   - `ruff check`: **PASS (0 errors)**

---

## 4. Phase 9 Deliverables Checklist

| Deliverable | Location | Status |
| :--- | :--- | :--- |
| **Candidate & Rule Domain Models** | `core/windagent_core/domain/candidate.py` | Complete |
| **Candidate Generator & Miner** | `intelligence/windagent_intelligence/candidate/candidate_generator.py` | Complete |
| **Eligibility Gate** | `intelligence/windagent_intelligence/candidate/eligibility_gate.py` | Complete |
| **CandidateService Coordinator** | `intelligence/windagent_intelligence/candidate/service.py` | Complete |
| **Intelligence Package Exports** | `intelligence/windagent_intelligence/__init__.py` | Complete |
| **Storage ORM Models** | `storage/windagent_storage/orm/candidate_models.py` | Complete |
| **Alembic Migration 0026** | `storage/windagent_storage/migrations/alembic/versions/0026_candidate_learning.py` | Complete |
| **Candidate SQL Repository** | `storage/windagent_storage/repositories/candidate_repository.py` | Complete |
| **API V2 Candidates Router** | `apps/api/windagent_api/routers/v2_candidates.py` | Complete |
| **Phase 9 Test Suite** | `tests/component/intelligence/test_phase9_candidate_learning.py` | Complete |
| **Phase 9 Verdict JSON** | `artifacts/ban_ke_hoach_v1/phase_09/phase_09_verdict.json` | Complete |
| **Phase 9 Completion Report** | `artifacts/ban_ke_hoach_v1/phase_09/PHASE_09_REPORT.md` | Complete |

