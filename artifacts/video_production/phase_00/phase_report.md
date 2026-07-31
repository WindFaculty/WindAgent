# Phase 0 — Baseline freeze report

Status: `PASSED`

The frozen baseline `1d98e26fe8923549e848e1a73cf32c6bb59944c1` was certified from a clean detached checkout. Its distinct Phase 7 evidence source is `6dab084abd3d46cc9f0c9e7dcbb6e65254b83057`; that relationship is explicit in `evidence_manifest.json` and is not rewritten as equality.

The KB-003 blocker was closed by commit `1d98e26` (build/verify finalizer refactor): `build` mode requires an explicit empty `--output-dir`, `verify` is strictly read-only, and the source-index builder, schemas, and hydrator tests are committed as companion files. The version-consistency checker now falls back to workspace `pyproject.toml` metadata.

From a clean detached checkout of the baseline, the full Python suite reported **949 passed, 3 skipped, 0 failed**. Architecture (0 violations), version consistency, runtime smoke, SQLite preflight (ephemeral `sqlite+aiosqlite` URL), CLI (21), and finalizer/hydrate tests (83) all passed. The tracked-tree SHA remained `98dc0d38082e715e8c17a36d9bd3cd6521296325` before and after — **0 tracked mutations**.

The exact GitHub Actions run `30456084211` supplied 13 immutable artifacts; all archive and extracted-tree digests verified. The gate `VP0_BASELINE_FROZEN` is now reproducible from a clean checkout and the baseline is ready to serve Phase 4.
