# Phase 7 Repair Inventory

## Baseline Information

- **Baseline SHA**: `6d9d5e0ba0419ace0efad7494e44392cbb2c705f` (HEAD at start of repair)
- **Branch**: `fix/phase7-verification-integrity`
- **Date**: 2026-07-29

## Git Status (at repair start)

```
On branch fix/phase7-verification-integrity
Changes not staged for commit:
  (use "git add/rm <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   .github/workflows/ci.yaml
	modified:   .github/workflows/phase14_multi_replica_fencing.yml
	modified:   apps/cli/windagent_cli/composition.py
	modified:   apps/cli/windagent_cli/main.py
	modified:   apps/desktop/src-tauri/Cargo.toml
	modified:   apps/desktop/src-tauri/gen/schemas/desktop-schema.json
	modified:   apps/desktop/src-tauri/gen/schemas/windows-schema.json
	modified:   artifacts/architecture_v2_production_hardening/phase_07/artifact_manifest.json
	modified:   artifacts/architecture_v2_production_hardening/phase_07/artifact_schema_report.json
	modified:   artifacts/architecture_v2_production_hardening/phase_07/runtime_version_report.json
	modified:   artifacts/architecture_v2_production_hardening/phase_07/version_consistency_report.json
	modified:   artifacts/architecture_v2_production_hardening/phase_07/version_manifest.json
	modified:   artifacts/architecture_v2_runtime_cutover/phase_13/import_graph.json
	modified:   ban_ke_hoach.md
	modified:   pyproject.toml
	modified:   scripts/check_version_consistency.py
	deleted:    scripts/schemas/artifact_schema.json
	modified:   tests/unit/cli/test_cli_commands.py
	modified:   tests/unit/cli/test_phase26_convergence.py
	modified:   uv.lock

Untracked files:
  (use "git add <file>..." to include what will be committed)
	artifacts/architecture_v2_production_hardening/phase_07/final/
	artifacts/architecture_v2_production_hardening/phase_07/phase5_completion.md
	artifacts/architecture_v2_runtime_cutover/CURRENT_VERDICT.json
	ci_remote.yaml
	ke_hoach_hoan_thien_phase_0_5.md
	run_claude_cli_openrouter.ps1
	tests/unit/cli/test_live_integration.py
```

## Git Diff Stats

```
 .github/workflows/ci.yaml                          |  134 +-
 .github/workflows/phase14_multi_replica_fencing.yml |   11 +-
 apps/cli/windagent_cli/composition.py              |  610 +++++-
 apps/cli/windagent_cli/main.py                     |  422 +++-
 apps/desktop/src-tauri/Cargo.toml                  |    1 +-
 apps/desktop/src-tauri/gen/schemas/desktop-schema.json |   1 +-
 apps/desktop/src-tauri/gen/schemas/windows-schema.json |   1 +-
 artifacts/architecture_v2_production_hardening/phase_07/artifact_manifest.json |   82 +-
 artifacts/architecture_v2_production_hardening/phase_07/artifact_schema_report.json |  140 +-
 artifacts/architecture_v2_production_hardening/phase_07/runtime_version_report.json |   72 +-
 artifacts/architecture_v2_production_hardening/phase_07/version_consistency_report.json |   48 +-
 artifacts/architecture_v2_production_hardening/phase_07/version_manifest.json |    2 +-
 artifacts/architecture_v2_runtime_cutover/phase_13/import_graph.json |  374 +++-
 ban_ke_hoach.md                                    | 2149 ++++++++------------
 pyproject.toml                                     |    3 +-
 scripts/check_version_consistency.py               |   37 +-
 scripts/schemas/artifact_schema.json               |  145 --
 tests/unit/cli/test_cli_commands.py                |   28 +-
 tests/unit/cli/test_phase26_convergence.py         |   20 +-
 uv.lock                                            |  319 ++-
 17 files changed, 2859 insertions(+), 1737 deletions(-)
```

## Change Classification

### Phase 1 — Artifact Protocol
| File | Classification | Rationale |
|------|----------------|-----------|
| `scripts/schemas/artifact_schema.json` (deleted) | **Phase 1** | Old duplicate schema removed; canonical is `artifact_protocol_v1.schema.json` |
| `artifacts/.../phase_07/artifact_manifest.json` | **Phase 1** | Production artifact manifest modified |
| `artifacts/.../phase_07/artifact_schema_report.json` | **Phase 1** | Schema validation report modified |
| `scripts/check_version_consistency.py` | **Phase 1/5 overlap** | Version checker fixes (also used in CI) |

### Phase 2 — Evidence Pipeline
| File | Classification | Rationale |
|------|----------------|-----------|
| `artifacts/.../phase_07/runtime_version_report.json` | **Phase 2** | Runtime evidence artifact modified |
| `artifacts/.../phase_07/version_consistency_report.json` | **Phase 2** | Version evidence artifact modified |
| `artifacts/.../phase_07/version_manifest.json` | **Phase 2** | Version manifest modified |

### Phase 3 — CLI Architecture
| File | Classification | Rationale |
|------|----------------|-----------|
| `apps/cli/windagent_cli/composition.py` | **Phase 3** | CLI composition/architecture check logic modified |
| `apps/cli/windagent_cli/main.py` | **Phase 3** | CLI entry point and architecture command modified |
| `tests/unit/cli/test_cli_commands.py` | **Phase 3/4 overlap** | CLI command tests modified |
| `tests/unit/cli/test_phase26_convergence.py` | **Phase 3/4 overlap** | CLI convergence tests modified |
| `tests/unit/cli/test_live_integration.py` (untracked) | **Phase 3/4 overlap** | New CLI live integration test |

### Phase 4 — CLI Runtime Truthfulness
| File | Classification | Rationale |
|------|----------------|-----------|
| `apps/cli/windagent_cli/composition.py` | **Phase 4** | CLI composition modified for truthfulness |
| `apps/cli/windagent_cli/main.py` | **Phase 4** | CLI main modified for truthfulness |
| `tests/unit/cli/test_cli_commands.py` | **Phase 4** | CLI command tests for truthfulness |
| `tests/unit/cli/test_live_integration.py` (untracked) | **Phase 4** | Live integration tests |

### Phase 5 — CI Matrix
| File | Classification | Rationale |
|------|----------------|-----------|
| `.github/workflows/ci.yaml` | **Phase 5** | Complete CI workflow rewrite |
| `.github/workflows/phase14_multi_replica_fencing.yml` | **Phase 5** | Trigger configuration for fencing workflow |
| `scripts/check_version_consistency.py` | **Phase 5** | Version checker for CI fail-closed |
| `artifacts/.../phase_13/import_graph.json` | **Phase 5** | CI artifact |

### Unrelated / User-Owned (Do Not Modify)
| File | Classification | Rationale |
|------|----------------|-----------|
| `apps/desktop/src-tauri/Cargo.toml` | **Unrelated** | Desktop Tauri config - user-owned |
| `apps/desktop/src-tauri/gen/schemas/desktop-schema.json` | **Unrelated** | Generated desktop schema - user-owned |
| `apps/desktop/src-tauri/gen/schemas/windows-schema.json` | **Unrelated** | Generated windows schema - user-owned |
| `artifacts/.../phase_13/import_graph.json` | **Unrelated** | Different phase artifact - historical |
| `ban_ke_hoach.md` | **User-owned** | Vietnamese planning doc - user-owned |
| `pyproject.toml` | **Unrelated** | Workspace config - minor change |
| `uv.lock` | **Unrelated** | Lockfile - auto-generated |
| `ci_remote.yaml` (untracked) | **Unrelated** | CI config variant - user-owned |
| `ke_hoach_hoan_thien_phase_0_5.md` (untracked) | **User-owned** | This repair plan - user-owned |
| `run_claude_cli_openrouter.ps1` (untracked) | **User-owned** | User script - user-owned |
| `artifacts/.../runtime_cutover/CURRENT_VERDICT.json` (untracked) | **Unrelated** | Different phase verdict - historical |
| `artifacts/.../phase_07/final/` (untracked dir) | **Unrelated** | Different artifact directory |

## Repair Principles (Per Plan)

1. **No direct modification of `main` branch**
2. **No `git reset --hard`, `git checkout --`, or deletion of unowned changes**
3. **Worktree classification before any implementation**
4. **Verdicts derived from gates only — no manual PASS entry**
5. **Test pass ≠ gate pass without acceptance contract coverage**
6. **Production artifacts validated by exact CI command**
7. **CI only valid on candidate commit SHA**
8. **New commit + full CI rerun if code changes after CI starts**

## Phase 0 Gates (Entry Criteria for Phase 1)

- [x] G0.1 Baseline SHA and branch lineage confirmed
- [x] G0.2 Verdict authoritative is BLOCKED
- [x] G0.3 Risk register has complete OPEN P0/P1
- [x] G0.4 Phase 5 completion report marked provisional
- [x] G0.5 No implementation changes in Phase 0 closure commit

## Phase 0 Completion Commit

Once all gates pass, create commit:
```
docs(phase7-repair): reconcile blocked verdict and open risks

- Update phase_verdict.md with authoritative metadata (BLOCKED)
- Update risk_register.md with OPEN P0/P1 risks
- Add repair_inventory.md baseline snapshot
- Mark phase5_completion.md as provisional
- No implementation changes in this commit
```