# Phase 0-7 Repair — Authoritative Risk Register

All P0 risks (R11–R13, R17) and P1 risks (R14–R16) are CLOSED. Risk R18 remains OPEN because GitHub branch protection rules on `main` could not be verified (HTTP 404).

| ID | Risk | Priority | Control | Status |
|---|---|---:|---|---|
| R11 | Artifact schema integrity | P0 | Canonical JSON Schema + automated schema validation on all artifacts | `CLOSED` |
| R12 | Evidence publication integrity | P0 | Verified SHA evidence bundle with sha256 manifests | `CLOSED` |
| R13 | Command receipt authenticity | P0 | Secrets redacted before persistence; stdout/stderr and combined hashes recomputed | `CLOSED` |
| R14 | CLI architecture exit contract | P1 | Typed JSON failures and stable exits for violation, root missing, missing checker, crash and timeout | `CLOSED` |
| R15 | CLI runtime truthfulness | P1 | Zero hardcoded demo fallbacks; real runtime checks | `CLOSED` |
| R16 | Cross-platform CI integrity | P1 | 13-job CI matrix passing on Ubuntu and Windows | `CLOSED` |
| R17 | Candidate identity drift | P0 | Candidate SHA `6dab084abd3d46cc9f0c9e7dcbb6e65254b83057` recorded across environment and bundles | `CLOSED` |
| R18 | Required-check bypass | P1 | Branch protection on `main` unverified (HTTP 404: Branch not protected) | `OPEN` |

## Summary

- Open P0 Risks: 0
- Open P1 Risks: 1 (R18)
- Open P2 Risks: 0
- Final Verdict: `PHASE_7_FINAL_EVIDENCE_BLOCKED`
