# Phase 7 Risk Register

| ID | Risk | Likelihood | Impact | Mitigation | Status |
|----|------|------------|--------|------------|--------|
| R1 | Version drift between packages | Low | High | Single canonical source (`windagent_core.version`), automated checker | CLOSED |
| R2 | Scaffold generator strips public exports | Medium | High | Updated scaffold preserves re-exports, tests verify | CLOSED |
| R3 | Artifact schema validator accepts invalid artifacts | Low | High | 7 negative fixtures with distinct failure reasons | CLOSED |
| R4 | CLI architecture-check fails from subdirs | Low | Medium | Root detection walks to pyproject.toml | CLOSED |
| R5 | Documentation references legacy apps/backend | Low | Medium | All legacy refs removed or marked historical | CLOSED |
| R6 | CI gates masked by `|| true` or continue-on-error | Low | Critical | Verified no masking in `.github/workflows/ci.yaml` | CLOSED |
| R7 | CURRENT_VERDICT points to provisional SHA | Low | High | Points to final verified SHA `09ce71b8dd5851cce6f2e741f8ac94bf25e81378` | CLOSED |
| R8 | Desktop/web version mismatch not flagged | Medium | Low | Warning only (intentional independent versioning) | ACCEPTED |
| R9 | Single skipped test not a gate | Low | Low | `test_disabled_rules_are_skipped` tests disabled behavior | ACCEPTED |
| R10 | Source checkout without installed metadata | Medium | Medium | Fallback to pyproject.toml with controlled canonical version | CLOSED |

All critical risks closed. Two accepted risks documented with rationale.
