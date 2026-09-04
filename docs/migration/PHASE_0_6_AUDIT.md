# Phase 0–6 reassessment

Date: 2026-09-02

This audit compares `ban_ke_hoach.md` with executable code and gates rather
than relying on the previous status board.

| Phase | Result | Evidence | Follow-up completed |
| --- | --- | --- | --- |
| 0 — freeze | Complete | Old repository HEAD is exactly `01695ca48dddb7220efd60c212e52dac1d6a5f2d`; 56 manifest rows pass the validator. Dirty old-tree changes remain excluded as documented. | None required. |
| 1 — repository | Complete after correction | uv, Ruff, mypy strict, pytest, frontend typecheck/test all pass; CI contains lint/type/unit/architecture/security/build. | Added the missing frontend build command to `scripts/run_gates.ps1`. |
| 2 — kernel | Complete | IDs, errors/result, event envelope, clock, money, version and JSON values are unit-tested; the standard-library-only architecture gate passes. | None required. |
| 3 — contracts | Complete | Command/query/module/job/event/UoW/artifact/security/telemetry ports and domain-neutral architecture gates pass. | Phase 7 extends the deliberately deferred job reliability surface without adding feature vocabulary. |
| 4 — module runtime | Complete | Discovery, whole-set validation and ordered registration pass. | Added `WorkerModuleRuntime`, proving discovered `JobRegistration` values populate the worker registry without worker-engine edits. |
| 5 — persistence | Complete | PostgreSQL-only startup rule, async SQL UoW, CAS/helpers, clean `0001`, offline migration, unit gates, and live PostgreSQL integration gates pass. | Integration fixture now upgrades the shared CI/database container to `head`; the CAS integration fixture was corrected to seed its initial versioned row explicitly. |
| 6 — events/outbox | Complete | Atomic event+outbox, deduplication, lease/CAS publisher, retry/dead-letter, recovery, and live PostgreSQL tests pass; migration `0002` remains clean. | The integration bootstrap correction makes the suite self-contained on a fresh PostgreSQL service. |

Local reassessment result before Phase 7 implementation:

```text
phase0 manifests     PASS (56)
ruff                 PASS
mypy strict          PASS
backend tests        PASS (130 passed, 9 PostgreSQL skipped)
frontend typecheck   PASS
frontend tests       PASS
```

The skips are environmental, not silently treated as green: Docker Desktop
was unavailable and the machine-local PostgreSQL service did not accept the
project credentials. The CI PostgreSQL job remains the certification gate.

Final local regression after completing Phase 7 and certifying PostgreSQL:

```text
phase0 manifests     PASS (56)
ruff                 PASS
mypy strict          PASS (119 source files)
backend tests        PASS (162 passed, 0 skipped)
PostgreSQL suite     PASS (12 passed)
frontend typecheck   PASS
frontend tests       PASS (5 files, 9 tests)
frontend build       PASS
pip-audit            PASS (no known third-party vulnerabilities)
npm audit            PASS (0 vulnerabilities)
```
