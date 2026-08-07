# Browser Session Recovery Policy

## 1. Overview

Browser session recovery testing validates that if a worker process crashes or the browser session closes after submitting a generation job, the workflow recovers gracefully without submitting duplicate jobs or wasting credit budget.

## 2. Recovery Test Procedure

1. **Submit Generation**: Submit image/video generation job to Flow backend. Record `job_id` and request hash.
2. **Controlled Session Disconnect**: Simulate browser disconnect or worker crash before download completes.
3. **Workflow Pause Transition**: Verify workflow enters `PAUSED_RECOVERY` state.
4. **Session Re-attach**: Re-establish browser automation session and query existing job registry.
5. **Job Reconciliation**: Confirm the worker reconciles existing `job_id`, waits for completion, and downloads results without re-submitting the generation request.

## 3. Duplicate Submit Zero-Tolerance Rule

Any duplicate job submission detected during recovery test causes immediate failure of gate `VP24_E2E_POC_PASSED`.
