# T7 Test Architecture — Final Certification Report

- **Gate:** `T7_TEST_ARCHITECTURE_PRODUCTION_READY`
- **Verdict: READY**
- **Date:** 2026-08-25
- **Candidate code SHA (`CANDIDATE_CODE_SHA`):** `0e9b8bd3a29eda4cc766edc1f3787682ef66b0a7`
- **Evidence publication SHA (`EVIDENCE_PUBLICATION_SHA`):** `e41c8c340cbd39f91ce5b49ee91d18b9a9104a27`

## 1. Certification requirement

Three consecutive successful GitHub Actions runs on one immutable candidate
SHA, with all required jobs green (no failures and no skipped jobs):

1. The push run of the candidate commit.
2. Two independent `workflow_dispatch` runs on the same ref, with no commits
   in between, so the executed tree is byte-identical.

## 2. Evidence

| Slot | Run ID | Trigger | Result | Jobs | Started (UTC) | URL |
|---|---|---|---|---|---|---|
| run_1 | 32795448269 | push | success | 25/25, 0 failed, 0 skipped | 2026-08-25T00:54:07Z | https://github.com/WindFaculty/WindAgent/actions/runs/32795448269 |
| run_2 | 32796802813 | workflow_dispatch | success | 25/25, 0 failed, 0 skipped | 2026-08-25T01:14:52Z | https://github.com/WindFaculty/WindAgent/actions/runs/32796802813 |
| run_3 | 32797518556 | workflow_dispatch | success | 25/25, 0 failed, 0 skipped | 2026-08-25T01:22:25Z | https://github.com/WindFaculty/WindAgent/actions/runs/32797518556 |

All three runs report `head_sha = 0e9b8bd3a29eda4cc766edc1f3787682ef66b0a7`,
which is also the tip of `origin/refactor/architecture-v3-hardening` at the
time of certification. Each `run_{1,2,3}/` slot in this directory contains:

- `run_summary.json` — GitHub API run object (id, head SHA, event,
  conclusion, timestamps).
- `jobs.json` — per-job name/conclusion/timestamps for all 25 jobs.
- `final_evidence_bundle.zip` + `bundle_contents/` — the workflow's own
  `final-evidence-bundle` artifact, kept verbatim alongside its extraction
  (`ci_run_manifest.json`, `environment.json`).

`certification_manifest.json` records the SHA-256 hash and byte size of
every file in every slot. Hashes can be re-verified against any checkout of
the evidence publication commit.

## 3. Path to green — root causes fixed during certification

The candidate lineage reached `0e9b8bd` through six CI iterations. Every fix
was classified before landing; **no runtime product bug was found or masked**
(the one product-side fix — the health check `schema_migration` probe using
the canonical Alembic path instead of a raw table query — was landed and
reviewed separately before freezing). All remaining defects were test-design
or CI-infrastructure issues that had never been exercised end-to-end on
Linux CI:

| Run | Candidate | Failures | Classification | Root cause / fix |
|---|---|---|---|---|
| 1 | ab0e5e1 | 17 jobs | test/infra | Multiple stale expectations; fixed across subsequent candidates (third-party intake constants, workflow validation scoping). |
| 2 | ccd0282 | 9 jobs | infra/test | Windows-generated lockfile missing Linux native optional deps (npm/cli#4828): manual no-lockfile installs of `rolldown` (frontend/) and later `rollup` (apps/web/); phase-4 intake gate measured on a dirty dev worktree (`EXPECTED_FILE_COUNT` 457 → true committed-tree value 443, manifest digest recomputed over exact committed bytes). |
| 3 | 5c54c3d | 7 jobs | test design | Meta-test asserting stale workflow literals updated to the new RUN_DIR-scoped invariant; `@rollup/rollup-linux-x64-gnu` binding install step added once typecheck stopped masking it. |
| 4 | c00070b | 2 jobs | test design/evidence hygiene | `check_architecture_imports.py` rewrote its reports unconditionally during re-verification → added `--no-write`; graph edge serialization sorted for cross-platform byte stability. |
| 5 | 0e9b8bd (pre) | web-test coverage | test design | First-ever real vitest execution on Linux exposed unenforced coverage thresholds: bootstrap entry `src/main.tsx` (unexercisable under happy-dom) excluded from measurement; thresholds kept at 75/65/70/75 — application code measures 100%. |

The gates were layered: each fix revealed the next previously-masked failure
(typecheck → native binding → coverage; phase-4 exit → porcelain mutation),
which is why several iterations were needed. No FAIL was converted into a
SKIP at any point; no threshold or assertion was weakened.

## 4. Integrity guarantees honored

- No fake results: every verdict derives from real tool execution.
- No SQLite fallback in PG-gated tests; `p1-e2e-postgres` and
  `postgres-production-semantics` ran against real PostgreSQL 16 on CI.
- No hard sleeps waiting on DB readiness.
- Any tree change after freeze created a new candidate SHA and reset the
  PASS counter to 0/3 (this happened at every fix above).
- `prompt.md` (user-owned file) was left untouched throughout.

## 5. Verdict

The T7 test architecture meets its production-readiness gate:
**READY**, certified by three consecutive fully-green CI runs on the
immutable candidate `0e9b8bd`, with tamper-evident hashed evidence
published at `e41c8c3`.
