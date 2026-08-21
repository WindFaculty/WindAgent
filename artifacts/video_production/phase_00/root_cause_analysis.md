# Phase 0 — Root-cause analysis

## Confirmed chain

`6dab084…` is the source SHA of successful GitHub Actions run `30456084211`. That run produced 13 named `*-evidence` artifacts. The exact `web-test-evidence` artifact is still available as artifact ID `8725570639`, with GitHub digest `sha256:c418c781e21ab0512c9a054b33d72f051c62c478a5cf14c17e842928d6b947c0`.

The receipt inside that artifact, `web-test-evidence/receipts/build.json`, declares source `git_sha` `6dab084…` and succeeds. The unchanged CI-evidence validator also passes against all 13 artifacts when invoked with the CI workflow's full contract. The validator is therefore healthy and strict.

The Phase 0 baseline is different: `cbf725…`. Its tree differs from `6dab084…` by more than publication data—it includes the ignored-evidence rule, the Phase 7 finalizer, and the test that fails in a clean checkout. The attestation records the predecessor verified SHA but provides no machine-readable hydration/provenance map from `cbf725…` to the exact external artifacts.

## Why the clean baseline failed

The baseline test `test_finalizer_gate_evaluation` passes its repository root to `build_evidence_bundle` and leaves its `tmp_path` unused. The finalizer then reads `web-test-evidence`, `desktop-test-evidence`, and other CI artifact roots directly below that repository root.

Those directories are not source: `.gitignore` excludes `*-evidence/`; Git history contains no tracked `web-test-evidence/receipts/build.json`; and CI publishes the data only as GitHub Actions artifacts. A clean checkout therefore cannot satisfy the test without a verified hydrate step.

## Root-cause classification

| ID | Classification | Finding | Correct layer |
|---|---|---|---|
| VP0-BLOCKER-001 | Test defect | Unit test is coupled to external evidence root. | Test/verification boundary |
| VP0-BLOCKER-002 | Evidence hydration defect | Exact CI artifact exists but no reproducible local hydrate contract exists. | Manifest + hydrator |
| VP0-BLOCKER-003 | Manifest/provenance defect | `cbf725…` and `6dab084…` have distinct roles without a canonical mapping. | Provenance manifest/verifier |
| VP0-BLOCKER-004 | Manifest/provenance defect | The local Phase 0 command manifest omitted required validator arguments. | Test command manifest |

## Consequences for the fix

The fix must be an explicit manifest and fail-closed hydrator that accepts only an exact, verified artifact set, checks size and SHA-256, rejects path traversal, and records a receipt. The CI validator will be run unchanged with its complete argument contract. The Phase 0 verdict must separately record the attestation baseline SHA (`cbf725…`) and Phase 7 evidence source SHA (`6dab084…`).

No source code has been changed while producing this analysis. There are pre-existing user-owned modifications in `scripts/verification/finalize_phase7.py` and `tests/unit/verification/test_finalize_phase7.py`; they are deliberately untouched.

## Additional clean-checkout blocker

Hydration resolves the missing-evidence portion of the failure, but it cannot make the immutable baseline test clean. `test_finalizer_gate_evaluation` passes its checkout root to a finalizer that creates the tracked Phase 7 `final` directory and writes reports and manifests there; its `tmp_path` fixture is unused. A genuinely clean end-to-end rerun therefore requires a narrowly scoped future source/test change that injects a temporary output root or exposes a read-only verifier. The pre-existing user-owned changes to those exact files remain untouched by this Phase 0 work.

## Command-environment determinism

The first clean full-rerun attempt also showed that the `sqlite_preflight` argv is incomplete in an empty shell: `WINDAGENT_DATABASE_URL` is merely allowlisted, although the script requires it. Supplying a non-secret ephemeral SQLite URL made the command pass without changing the checkout. The command manifest is therefore amended with that value *template*, not a machine-specific database path or secret.
