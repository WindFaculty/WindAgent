# Phase 0-5 Repair — Worktree Inventory

## Lineage

- Baseline required by the repair plan: `601fd128` — confirmed ancestor of
  current HEAD.
- Repair-start snapshot: `6d9d5e0ba0419ace0efad7494e44392cbb2c705f`
  — confirmed ancestor of current HEAD.
- Current HEAD: `59e4fdf04ab43790e03ad8cb0be6a6bb6282bdd2`.
- Branch: `fix/phase7-verification-integrity`.
- Inventory date: 2026-07-29.

No repair commit or clean candidate is claimed by this document. The worktree
contains both repair changes and pre-existing/user-owned changes.

## Repair scope

| Area | Main paths | Classification |
|---|---|---|
| Phase 1 — artifact protocol | `scripts/schemas/*`, `scripts/validate_artifact_schema.py`, artifact fixtures | Repair-owned |
| Phase 2 — evidence pipeline | `scripts/verification/{capture_environment,generate_phase7_evidence,run_command_receipt,validate_evidence_bundle,validate_ci_evidence}.py` and tests | Repair-owned |
| Phase 3 — CLI architecture | `scripts/check_architecture_imports.py`, architecture fixtures/tests, repository-root discovery | Repair-owned |
| Phase 4 — CLI truthfulness | `apps/cli/windagent_cli/{main,composition}.py`, shared tool registry, CLI tests | Mixed with earlier CLI work; preserve intent and review as one candidate |
| Phase 5 — CI | `.github/workflows/ci.yaml`, version checker, database/runtime/CI evidence helpers and tests | Repair-owned |
| Phase 0 — authority docs | This file, `phase_verdict.md`, `risk_register.md`, `phase5_completion.md` | Repair-owned |

The legacy duplicate `scripts/schemas/artifact_schema.json` is removed in favor
of `scripts/schemas/artifact_protocol_v1.schema.json`.

## Preserved pre-existing or user-owned changes

The repair does not discard, reset or overwrite the intent of these paths:

- `.github/workflows/phase14_multi_replica_fencing.yml`
- `apps/desktop/src-tauri/Cargo.toml`
- `apps/desktop/src-tauri/gen/schemas/*.json`
- `artifacts/architecture_v2_runtime_cutover/**`
- `ban_ke_hoach.md`
- `ci_remote.yaml`
- `ke_hoach_hoan_thien_phase_0_5.md`
- `run_claude_cli_openrouter.ps1`
- `pyproject.toml` and `uv.lock` changes that predate or support this repair

Generated local directories such as `.pytest_tmp/`, `apps/web/coverage/`,
`artifacts/ci/`, `test_repo/` and `test_repo2/` are not candidate source
evidence.

## Legacy Phase 7 artifact state

The earlier evidence generator removed a set of tracked, pre-protocol reports
from the production root and left an untracked legacy `evidence_bundle.json`
plus receipts. Those files were not valid under the repaired protocol:

- the bundle points to a different SHA;
- old receipts lack persisted stdout/stderr hashes;
- the old version report is not an artifact-protocol document.

The four authority Markdown files are restored with current truthful state.
The invalid local outputs were preserved, not deleted, under
`.pytest_tmp/legacy_phase_07_pre_protocol/2026-07-29-local/`. Other removed
tracked reports remain recoverable from Git history and must not be republished
as PASS evidence.

Two immutable local runs now exist under `phase_07/quarantine/`: the first is a
valid FAIL artifact recording sandbox temp/fixture failures; the second is a
valid BLOCKED artifact with all 8 required commands successful. Neither run
updates `latest.json`.

## Gate inventory

| Gate | State |
|---|---|
| G0.1 baseline lineage confirmed | PASS |
| G0.2 authoritative verdict is blocked | PASS |
| G0.3 P0/P1 risks are explicit | PASS |
| G0.4 Phase 5 report is provisional | PASS |
| G0.5 documentation-only Phase 0 commit | NOT CREATED; current worktree is mixed |
| Recursive validation of current production root | PASS — 18/18 JSON files |
| Clean candidate SHA and immutable evidence | PENDING |
| Remote 14-job CI run | PENDING |

## Safety constraints

- Do not use `git reset --hard`, `git checkout --` or destructive cleanup.
- Do not treat generated local output as authoritative candidate evidence.
- Do not mark PASS from local test output alone.
- Any code change after a CI run requires a new candidate SHA and full rerun.
