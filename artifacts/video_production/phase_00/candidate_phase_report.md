# VP0 candidate baseline attestation

`cbf7257643d4a1705fa221ae37e9391b6ee3f40e` remains the historical blocked baseline. Its hydrated finalizer test passed but rewrote 16 tracked files in a fresh rerun; the earlier inventory counted 17 because it included untracked `risk_register.md`.

Candidate `1d98e26fe8923549e848e1a73cf32c6bb59944c1` (on `fix/phase7-verification-integrity`, parent `cbf7257`) replaces the mutating finalizer with a build/verify refactor: `build` mode requires an explicit empty `--output-dir`, `verify` is strictly read-only, the CI-manifest fallback resolves from canonical evidence, and the source-index builder + schemas are first-class companions. The version-consistency checker now falls back to workspace `pyproject.toml` when package metadata is unavailable.

The candidate was re-certified from a clean detached checkout. Full Python (`949 passed, 3 skipped`), finalizer/hydrate tests (83 passed), architecture (0 violations), version consistency (PASSED), runtime smoke (PASS), SQLite preflight (PASS), and CLI (21 passed) all passed. The tracked-tree SHA remained `98dc0d38082e715e8c17a36d9bd3cd6521296325` before and after verification — **0 tracked mutations**. The immutable Phase 7 evidence remains mapped to its distinct source SHA `6dab084a`.

Verdict: `VP0_BASELINE_FROZEN = PASSED` for baseline `1d98e26`.
