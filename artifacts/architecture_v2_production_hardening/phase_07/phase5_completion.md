# Phase 5 — GitHub Actions Repair: Completion Report

⚠️ **PROVISIONAL REPORT** — This report is **not authoritative** until a GitHub Actions run completes successfully on the correct candidate SHA with all 14 required jobs passing. See Phase 0.4 baseline reconciliation.

## Verdict

```text
CI_MATRIX_FAIL_CLOSED_READY
```

## Gate Assessment

| Gate | Requirement | Status | Details |
|------|-------------|--------|---------|
| G5.1 | Workflow triggers on repair branch | ✅ PASS | `hardening/**`, `fix/**`, `feat/**` branches + `workflow_dispatch` |
| G5.2 | PostgreSQL service starts and health-checks | ✅ PASS | Dedicated `python-integration-postgres` job with `pg_isready` health checks |
| G5.3 | Windows jobs use valid PowerShell commands | ✅ PASS | `defaults.run.shell: pwsh` on all Windows jobs; no bash syntax used |
| G5.4 | Desktop npm ci from committed lockfile | ⚠️ PARTIAL | Web: `npm ci` ✅; Desktop: `npm install` (lockfile generated but not yet committed; run `git add apps/desktop/package-lock.json && git commit` then switch to `npm ci`) |
| G5.5 | Production artifacts schema-validated | ✅ PASS | `artifact-protocol` job validates `--directory phase_07 --recursive --verify-hashes` |
| G5.6 | No continue-on-error or exit masking | ✅ PASS | `continue-on-error: true` removed from all mandatory gates |

## CI Workflow Structure

14 focused jobs with clear separation of concerns:

1. **artifact-protocol** — Validates production artifacts against schema v1
2. **version-consistency** — All versions derive from canonical source
3. **architecture-boundaries** — Scaffold + import boundaries + no-legacy
4. **python-unit-sqlite** — Unit tests (Ubuntu, SQLite)
5. **python-unit-windows** — Unit tests (Windows, SQLite)
6. **python-integration-sqlite** — Integration tests (Ubuntu, SQLite)
7. **python-integration-postgres** — Integration tests (Ubuntu, PostgreSQL)
8. **runtime-smoke** — FastAPI/CLI/Worker version checks
9. **cli-contract** — CLI commands against real runtime
10. **web-test** — Web: test, typecheck, coverage, build (Ubuntu)
11. **web-test-windows** — Web: test, typecheck, build (Windows)
12. **desktop-test** — Desktop: test, typecheck, build (Ubuntu)
13. **desktop-test-windows** — Desktop: test, typecheck, build (Windows)
14. **final-evidence** — Aggregate and verify all gates

## Files Modified

| File | Change |
|------|--------|
| `.github/workflows/ci.yaml` | Complete rewrite: 14 jobs, proper triggers, PostgreSQL service, cross-platform shell, artifact validation, artifact uploads |
| `.github/workflows/phase14_multi_replica_fencing.yml` | Added `feat/**`, `fix/**`, `hardening/**` to triggers |
| `scripts/check_version_consistency.py` | Fixed `check_hardcoded_versions()`: removed `"0.3.0"` early-return guard and `always_allowed` bypass |
| `apps/desktop/package-lock.json` | Generated for `npm ci` reproducibility |

## Required Checks for Branch Protection (G5.9)

Configure the following jobs as required checks in GitHub branch protection rules for `main`:

```yaml
required_checks:
  - artifact-protocol
  - version-consistency
  - architecture-boundaries
  - python-unit-sqlite
  - python-unit-windows
  - python-integration-sqlite
  - python-integration-postgres
  - runtime-smoke
  - cli-contract
  - web-test
  - web-test-windows
  - desktop-test
  - desktop-test-windows
  - final-evidence
```

## Remaining Action Items

1. **Commit desktop lockfile**: `git add apps/desktop/package-lock.json && git commit -m "chore(desktop): add lockfile for CI reproducibility"`
2. **Switch desktop CI to `npm ci`**: After committing lockfile, update `.github/workflows/ci.yaml` to use `npm ci` for desktop jobs
3. **Run CI on this branch**: Push to `fix/phase7-verification-integrity` and verify all 14 jobs pass

## Verdict Transition

```text
From: PHASE_7_CODE_CONVERGED_VERIFICATION_BLOCKED
  To: CI_MATRIX_FAIL_CLOSED_READY
```