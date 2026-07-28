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

---

## Phase 0–5 OPEN Risks (Blocking Phase 6 Readiness)

| ID | Risk | Priority | Phase | Details |
|----|------|----------|-------|---------|
| R11 | Artifact schema integrity | **OPEN / P0** | Phase 1 | Schema validator rejects self-hashes, placeholder hashes, empty commands/hashes; flags must be additive; git SHA semantics enforced |
| R12 | CI evidence integrity | **OPEN / P0** | Phase 2 | Failed runs must not publish; publish must be atomic/immutable; receipts must link to redacted logs |
| R13 | Command receipt authenticity | **OPEN / P0** | Phase 2 | Output hashes must match persisted redacted logs; secrets redacted before persistence |
| R14 | CLI architecture exit contract | **OPEN / P1** | Phase 3 | Required checkers must all execute; missing checker = exit 3; crash/timeout = exit 4; violation = exit 1; root missing = exit 2 |
| R15 | CLI runtime truthfulness | **OPEN / P1** | Phase 4 | No fabricated production values; demo only with `--demo`; data_source in every JSON; read commands don't mutate |
| R16 | Cross-platform CI | **OPEN / P1** | Phase 5 | Windows jobs use pwsh; PostgreSQL on Ubuntu; npm ci with committed lockfiles; no fallback masking |

---

**Note**: The statement "All critical risks closed" from the previous risk register is **retracted**. Six P0/P1 risks (R11–R16) remain open and block Phase 6 readiness.