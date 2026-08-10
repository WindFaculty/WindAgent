# STUDIO_API_GATE — C1 verdict

- Contract: studio.contract/v0.1
- Gate: STUDIO_API_GATE
- Verdict: **FAIL**
- Integration SHA: `03d2cfb9fb12875ed10c5aa41beca58120d6a497`
- Generated: 2026-08-10T03:30:59.158217+00:00

## Checks

- FAIL — contract_suite_passes
- PASS — frozen_endpoints_implemented
- PASS — no_unfrozen_extra_routes
- PASS — snapshot_matches_openapi
- PASS — no_sample_ids_in_v3_surface

## Surface

- Frozen endpoints implemented: 13
- Live V3 paths: 15
- OpenAPI snapshot SHA256: `412968eb1548fb04b0886bcb8f7cf9a46bdedd9b19d49937048f9e21143a1171`
- Missing frozen endpoints: none
- Extra unfrozen routes: none

## Test results

- `pytest tests/unit/api/test_studio_v3_api.py -q` → 2 failed, 29 passed in 13.17s

## Composition

- orchestrator port None until A4 handoff; mutations return CAPABILITY_UNAVAILABLE; reads served by A3 SQL adapters.

Evidence JSON: `artifacts/studio_roadmap_01/c1/evidence.json`
