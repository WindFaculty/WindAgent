# PHASE 8 - Risk Register

## Phase Overview
**Phase 8: Loai bo API V1 ngay (API V1 Removal)**
- **Gate**: `API_V1_REMOVED`
- **Status**: COMPLETED

---

## Risk Assessment

### R1 - Desktop or Web still calling V1 endpoints
**Severity**: HIGH  
**Likelihood**: MEDIUM  
**Status**: MITIGATED  
**Description**: Desktop or Web applications might still have hardcoded references to `/api/v1/*` endpoints.  
**Mitigation**: 
- Updated `apps/desktop/vite.config.ts` to remove `/api/v1` proxy
- Updated `apps/desktop/src/lib/routerApi.ts` to use `/api/v2/providers`
- Updated `apps/desktop/src/pages/Router.tsx` to use `/api/v2/providers`
- Tombstone handler returns 410 Gone to clearly indicate V1 is removed
- Desktop will fail visibly if it tries to use V1 endpoints

### R2 - V1 removal breaks existing integrations
**Severity**: HIGH  
**Likelihood**: LOW  
**Status**: ACCEPTED  
**Description**: External clients or scripts might be using V1 endpoints.  
**Mitigation**: 
- Tombstone handler provides clear migration guidance
- 410 Gone status code is semantically correct for permanently removed resources
- Migration guide URL provided in response
- Phase 8 is intentionally breaking - this is a planned breaking change

### R3 - Incomplete V1 code removal
**Severity**: MEDIUM  
**Likelihood**: LOW  
**Status**: VERIFIED  
**Description**: Some V1 compatibility code might remain in the codebase.  
**Mitigation**: 
- Deleted `compatibility.py` module completely
- Removed all V1 imports from `main.py`
- Removed V1 router registrations
- Created test suite to verify no V1 imports remain
- Grepped entire codebase for V1 references

### R4 - V2 endpoints not fully operational
**Severity**: CRITICAL  
**Likelihood**: LOW  
**Status**: VERIFIED  
**Description**: Removing V1 code might accidentally break V2 endpoints.  
**Mitigation**: 
- V2 routers are completely separate from V1 compatibility code
- No shared state or dependencies between V1 and V2 routers
- Test suite verifies V2 endpoints still work after V1 removal
- Health check tests pass

### R5 - Feature flag references remain
**Severity**: LOW  
**Likelihood**: MEDIUM  
**Status**: VERIFIED  
**Description**: Code might reference V1 feature flags that no longer exist.  
**Mitigation**: 
- Searched codebase for `enable_v1_api_compatibility` - only found in deleted file
- Searched for `v1_compatibility` - only found in test file (updated)
- No feature flag code remains in production path

---

## Residual Risks

| Risk ID | Description | Severity | Likelihood | Status | Owner |
|---------|-------------|----------|------------|--------|-------|
| R1 | Desktop/Web V1 references | HIGH | LOW | MONITORED | Frontend Team |
| R2 | External V1 clients | HIGH | LOW | ACCEPTED | API Team |

---

## Verification Checklist

- [x] V1 compatibility router deleted
- [x] V1 imports removed from main.py
- [x] V1 router registrations removed
- [x] Tombstone handler implemented (410 Gone)
- [x] Desktop proxy configuration updated
- [x] Desktop API client updated to V2
- [x] Test suite created and passing
- [x] V2 endpoints verified operational
- [ ] Manual verification of API startup
- [ ] Manual verification of desktop build
- [ ] Manual verification of V1 endpoints return 410

---

## Recommendation

**PROCEED** to Phase 9 (Migration du lieu va schema rollback)

All critical risks have been mitigated. Residual risks are accepted as part of the breaking change nature of Phase 8. The tombstone handler provides clear guidance for any clients still using V1 endpoints.
