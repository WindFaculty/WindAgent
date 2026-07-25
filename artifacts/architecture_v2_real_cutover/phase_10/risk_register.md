# PHASE 10 - Risk Register

## Phase Overview
- **Phase Number**: 10
- **Phase Name**: Readiness, Liveness and Diagnostics
- **Gate**: `HEALTH_AND_DIAGNOSTICS_TRUSTWORTHY`
- **Execution Date**: 2026-07-25

---

## Risk Assessment

### R1 - Database Connection Failures During Health Checks

**Severity**: HIGH  
**Likelihood**: MEDIUM  
**Status**: **MITIGATED**

**Description**: 
Health checks perform real database queries. If the database is slow or unavailable, health checks could fail and cause the API to return 503 even when it could serve requests from cache.

**Impact**:
- API returns 503 Service Unavailable during database outages
- Clients may see degraded service even when some functionality works
- Cascade failures in distributed systems

**Mitigation**:
- Health checks use lightweight queries (`SELECT 1`)
- Database connection pool is reused from existing infrastructure
- Health checks have their own timeouts separate from main application timeouts
- Fail-closed behavior ensures we don't lie about readiness
- In DEVELOPMENT profile, database is not required (NOT_REQUIRED status)

**Contingency**:
- If database is unavailable, API correctly returns 503
- Clients can implement retry logic
- Monitoring can alert on health check failures

---

### R2 - Hardcoded Values Not Fully Eliminated

**Severity**: CRITICAL  
**Likelihood**: LOW  
**Status**: **MITIGATED**

**Description**: 
Original health checks in `apps/api/windagent_api/health.py` had hardcoded values that could mask real problems:
- Schema version: `"v2_canonical_latest"`
- Outbox pending records: `0`
- Event bus: `"Event bus ready"`

**Impact**:
- False sense of health
- Production outages not detected
- Violates fail-closed principle

**Mitigation**:
- All hardcoded values replaced with real checks via HealthChecker service
- Each check now queries real state:
  - Schema version: Queries `migration_history` table
  - Outbox: Counts pending/failed records from `outbox_records` table
  - Event bus: Checks EventDispatcher instance
- Comprehensive test coverage to prevent regression

**Verification**:
- All acceptance criteria in `test_phase10_health_endpoints.py` verify no hardcoded values
- Manual verification: No string literals for health values in health.py

---

### R3 - Worker Status Query Dependency

**Severity**: HIGH  
**Likelihood**: MEDIUM  
**Status**: **MITIGATED**

**Description**: 
Worker heartbeat status is checked via `SqlWorkerHeartbeatRepository`. If this repository is not properly initialized or the table doesn't exist, the check could fail.

**Impact**:
- Worker status incorrectly reported as DOWN when it's actually UP
- Or vice versa: Worker reported as UP when it's DOWN
- In PRODUCTION profile: API refuses to start without worker

**Mitigation**:
- Worker status query is initialized in ApplicationContainer with proper dependency injection
- Check gracefully handles missing table (returns DOWN with error details)
- In DEVELOPMENT profile: Worker not required, returns DEGRADED instead of failing
- Worker heartbeat table is created as part of migration_001

**Contingency**:
- If worker status cannot be determined: Returns DOWN with error details
- Clients see explicit error in health check response

---

### R4 - Registry Loading Side Effects

**Severity**: MEDIUM  
**Likelihood**: MEDIUM  
**Status**: **MITIGATED**

**Description**: 
Health checks call methods on registries (`list_providers()`, `list_tools()`, etc.). These methods might have side effects or be slow.

**Impact**:
- Health check latency increased
- Potential resource exhaustion from repeated registry scans
- Side effects from list methods (unlikely but possible)

**Mitigation**:
- Registry list methods are designed to be lightweight
- Health checks are cached at the FastAPI level (HealthChecker instance in app.state)
- Each check is executed concurrently with others using asyncio.gather
- Registries are initialized once and reused

**Contingency**:
- Add caching layer for registry health checks if performance becomes an issue
- Make registry checks optional in TEST profile

---

### R5 - Filesystem Path Checks Too Strict

**Severity**: LOW  
**Likelihood**: LOW  
**Status**: **ACCEPTED**

**Description**: 
Filesystem health check verifies existence of paths like `scripts/`, `configs/`, `storage/`. In some deployment scenarios (Docker, packaged), these paths might not exist or be at different locations.

**Impact**:
- False health check failures in valid deployments
- Requires configuration of required paths per deployment

**Mitigation**:
- Only checks for default paths that should exist in development
- Custom paths can be passed to HealthChecker constructor
- Missing paths return DOWN with clear error message showing which paths are missing

**Contingency**:
- Allow disabling filesystem checks via configuration
- Make filesystem checks NOT_REQUIRED in certain profiles

---

### R6 - Configuration Validity Check Incomplete

**Severity**: LOW  
**Likelihood**: MEDIUM  
**Status**: **ACCEPTED**

**Description**: 
Current configuration check only validates that WINDAGENT_ENV exists and maps to a valid profile. It doesn't validate all required configuration (database URL, provider keys, etc.).

**Impact**:
- Configuration errors might not be caught by health checks
- Application could start with invalid configuration and fail later

**Mitigation**:
- Configuration check is extensible and can be enhanced
- Fail-closed principle: If configuration is truly invalid, application will fail on startup anyway
- Current check validates core environment setup

**Future Work**:
- Enhance configuration validation to check required settings
- Add schema validation for configuration values
- Test that invalid configurations cause health check to fail

---

### R7 - Outbox Table Might Not Exist

**Severity**: MEDIUM  
**Likelihood**: HIGH (during initial setup)  
**Status**: **MITIGATED**

**Description**: 
Outbox health check queries the `outbox_records` table. This table might not exist in fresh databases or before migrations are applied.

**Impact**:
- Outbox check returns DOWN with "table not found" error
- Overall readiness might fail even though this is expected during setup

**Mitigation**:
- Check catches "no such table" exception and returns DOWN with clear message
- Outbox table is created in migration_001 (initial schema)
- In TEST profile: Outbox check is NOT_REQUIRED

**Contingency**:
- Schema migration should be run before starting the application
- Health check failure correctly indicates that setup is incomplete

---

### R8 - Profile Detection Inconsistency

**Severity**: MEDIUM  
**Likelihood**: LOW  
**Status**: **MITIGATED**

**Description**: 
Profile is detected from multiple sources (bootstrap_config.env, os.environ, defaults). There could be inconsistency between API and CLI if they read from different sources.

**Impact**:
- Different behavior between API /health/ready and CLI windagent doctor
- Confusing for users

**Mitigation**:
- Both API and CLI use the same HealthChecker service
- Profile detection follows same precedence: explicit > env var > default
- Consistent environment variable name: WINDAGENT_ENV
- Default to DEVELOPMENT for safety

**Verification**:
- Tests verify profile is consistent in HealthChecker
- Manual testing confirms API and CLI report same profile

---

### R9 - Health Check Performance in Production

**Severity**: MEDIUM  
**Likelihood**: MEDIUM  
**Status**: **ACCEPTED**

**Description**: 
Running all 13 health checks concurrently with asyncio.gather could have performance implications if some checks are slow (database queries, network calls in future).

**Impact**:
- Slow health check responses
- Health check timeouts
- Resource contention

**Mitigation**:
- All current checks are lightweight (local queries, in-memory checks)
- Checks run concurrently, not sequentially
- Database checks use existing connection pool
- Timeout can be added at the endpoint level

**Future Work**:
- Add per-check timeouts
- Add overall health check timeout
- Consider lazy/cached health checks for frequently-called endpoints
- Add metrics for health check latency

---

### R10 - Backward Compatibility

**Severity**: LOW  
**Likelihood**: LOW  
**Status**: **ACCEPTED**

**Description**: 
Clients that expect specific health check response format might break if the format changed significantly.

**Impact**:
- Clients parsing health check responses might need updates
- Monitoring systems expecting specific fields might break

**Mitigation**:
- Response format is backward compatible (still has status, checks, etc.)
- New fields (profile, required) are additive
- Structure of individual checks is consistent with previous format

**Verification**:
- Compared old and new response formats
- All required fields present in both
- New fields are optional from client perspective

---

## Risk Summary

| Risk ID | Severity | Likelihood | Status | Description |
|---------|----------|------------|--------|-------------|
| R1 | HIGH | MEDIUM | **MITIGATED** | Database connection failures during health checks |
| R2 | CRITICAL | LOW | **MITIGATED** | Hardcoded values not fully eliminated |
| R3 | HIGH | MEDIUM | **MITIGATED** | Worker status query dependency |
| R4 | MEDIUM | MEDIUM | **MITIGATED** | Registry loading side effects |
| R5 | LOW | LOW | **ACCEPTED** | Filesystem path checks too strict |
| R6 | LOW | MEDIUM | **ACCEPTED** | Configuration validity check incomplete |
| R7 | MEDIUM | HIGH | **MITIGATED** | Outbox table might not exist |
| R8 | MEDIUM | LOW | **MITIGATED** | Profile detection inconsistency |
| R9 | MEDIUM | MEDIUM | **ACCEPTED** | Health check performance in production |
| R10 | LOW | LOW | **ACCEPTED** | Backward compatibility |

## Overall Risk Assessment

**Current Status**: **PROCEED**  
**Confidence Level**: HIGH  

All CRITICAL and HIGH severity risks are MITIGATED. Remaining risks are LOW/MEDIUM severity and ACCEPTED with clear mitigation strategies. The implementation follows fail-closed principles and provides real health checks without hardcoded values.

## Recommendations for Production

1. **Monitor health check endpoints** in production to detect any unexpected failures
2. **Set appropriate health check intervals** based on check performance
3. **Configure load balancer timeouts** longer than health check execution time
4. **Alert on health check failures** to detect issues early
5. **Test health checks in staging** with production-like configuration before deploying

## Rollback Plan

If PHASE 10 causes issues:

1. **Rollback is simple**: Revert to previous health.py implementation
2. **No database changes**: PHASE 10 doesn't modify schema
3. **No breaking changes**: API contract is backward compatible
4. **Isolated changes**: Health check logic is contained in observability module

Steps:
```bash
git revert <phase-10-commit>
# Or selectively revert specific files
git checkout HEAD~1 -- apps/api/windagent_api/health.py
```

## Sign-off

- [x] All CRITICAL risks mitigated
- [x] All HIGH risks mitigated
- [x] MEDIUM risks accepted with clear mitigation
- [x] LOW risks documented
- [x] Rollback plan defined
- [x] Monitoring recommendations provided

**Risk Assessment Approver**: _________________________  
**Date**: 2026-07-25
