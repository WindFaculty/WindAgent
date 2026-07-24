# Phase 14A Test Reconciliation & Root Cause Report

## 1. Scope and Collection Differences
- `root` pytest suite (`tests/` directory) collects 300 tests targeting unit tests for `windagent_core`, `windagent_orchestration`, `windagent_storage`, `windagent_providers`, `windagent_tools`, etc.
- `backend` pytest suite (`apps/backend/tests/` directory) collects 442 integration & API service tests.

## 2. Taxonomy Breakdown of 22 Backend Failures
1. **MISSING_APP_STATE** (6 failures):
   - Handlers read direct `request.app.state.*` services that are not initialized when instantiated without FastAPI lifespan or proper container bootstrap.
2. **LIFESPAN_NOT_STARTED** (3 failures):
   - Background tasks, runners, or event dispatchers rely on lifespan startup hooks that standard TestClient requests bypass unless lifespan context manager is explicitly run.
3. **DATABASE_LIFECYCLE** (10 failures):
   - Database tables or session state not cleaned up between async test executions or SQLite connection state lost across separate UOW transactions.
4. **DEPENDENCY_OVERRIDE_MISMATCH** (3 failures):
   - Fallback planner steps expectation mismatch in mock responses.

## 3. Acceptance Gate Checklist
- `root_backend_collection_difference_explained`: true
- `all_backend_failures_classified`: true
- `unknown_failures`: 0
