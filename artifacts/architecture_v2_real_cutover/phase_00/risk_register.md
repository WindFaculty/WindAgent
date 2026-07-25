# PHASE 0 - Risk Register

## Baseline Assessment

**Date:** 2026-07-26  
**Commit:** 28d7fa1be11bbea954ee0977ee0252e2faabd1c7  
**Branch:** fix/architecture-v2-real-cutover

## Current State

### Test Results Summary
- **Total Tests:** 483
- **Passed:** 473
- **Failed:** 9
- **Skipped:** 1

### Failed Tests (Pre-existing, not caused by cutover)

1. **Integration Tests (6 failures)**
   - `test_execute_plan_endpoint_http` - 404 Not Found (endpoint not implemented)
   - `test_execute_plan_cycle_rejection` - 404 Not Found (endpoint not implemented)
   - `test_get_workflow_returns_durable_steps` - 404 Not Found (endpoint not implemented)
   - `test_get_runner_state_queries_durable_facts` - 404 Not Found (endpoint not implemented)
   - `test_pause_resume_stop_endpoints` - 404 Not Found (endpoint not implemented)
   - `test_retry_step_endpoint` - 404 Not Found (endpoint not implemented)
   
   **Root Cause:** API endpoints for workflow control are not yet implemented in the current state.

2. **Regression Test (1 failure)**
   - `test_def_006_startup_recovery_not_wired` - Recovery manager not wired in startup
   
   **Root Cause:** Startup recovery mechanism not yet implemented.

3. **Unit Tests (2 failures)**
   - `test_intelligence_no_forbidden_imports` - Intelligence imports orchestration (43 forbidden imports)
   - `test_legacy_compatibility_shim` - Depends object missing method
   
   **Root Cause:** 
   - Architecture boundary violation: Intelligence package imports from Orchestration
   - Incomplete migration of legacy compatibility layer

## Risk Classification

### HIGH RISK
- **Architecture Boundary Violations:** Intelligence → Orchestration imports (43 violations)
  - Impact: Violates dependency policy (providers → intelligence forbidden)
  - Mitigation: Must be resolved before PHASE 1

### MEDIUM RISK
- **Missing API Endpoints:** 6 integration tests fail due to 404
  - Impact: Functional gaps in API surface
  - Mitigation: Track in PHASE 2+ implementation

### LOW RISK
- **Legacy Compatibility Issues:** 2 unit test failures
  - Impact: Legacy shim incomplete
  - Mitigation: Resolve during migration phases

## Baseline Verdict

**BASELINE_VALID: YES**

The baseline is valid for starting the cutover process. The 9 failing tests represent **pre-existing issues** that must be tracked and resolved during subsequent phases, not blockers for PHASE 0 completion.

According to the plan: "Nếu baseline đang lỗi, không được quy lỗi cho cutover. Phải lập danh sách lỗi có sẵn."

This document serves as that list.

## Action Items

1. ✅ Document all pre-existing failures (this document)
2. ⏳ Track architecture boundary violations for PHASE 1 resolution
3. ⏳ Monitor integration test failures through migration phases
4. ⏳ Ensure legacy compatibility issues are addressed before legacy removal

## Sign-off

- Baseline commit: 28d7fa1be11bbea954ee0977ee0252e2faabd1c7
- Worktree: Clean
- Stashes: None
- Untracked files: None
- Branch: fix/architecture-v2-real-cutover (created from baseline)
