# Phase 7 — Final Risk Register

| ID | Risk | Priority | Control & Verification | Status |
|---|---|---:|---|---|
| R11 | Artifact schema integrity | P0 | Canonical JSON Schema + automated schema validation on all artifacts | `CLOSED` |
| R12 | Evidence publication integrity | P0 | Verified SHA evidence bundle with sha256 manifests | `CLOSED` |
| R13 | Command receipt authenticity | P0 | Secrets redacted before persistence; stdout/stderr and combined hashes recomputed | `CLOSED` |
| R14 | CLI architecture exit contract | P1 | Fail-closed CLI root detection and exit codes | `CLOSED` |
| R15 | CLI runtime truthfulness | P1 | Zero hardcoded demo fallbacks; real runtime checks | `CLOSED` |
| R16 | Cross-platform CI integrity | P1 | 13-job CI matrix passing on Ubuntu and Windows | `CLOSED` |
| R17 | Candidate identity drift | P0 | Candidate SHA match across git, manifest and receipts | `CLOSED` |
| R18 | Required-check bypass | P1 | Verified 13 required CI status checks; branch protection unverified | `OPEN` |
