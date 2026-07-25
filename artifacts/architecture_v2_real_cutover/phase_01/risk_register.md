# Phase 1 risk register

- HIGH: Full suite retains 9 Phase 0 baseline failures. No new checker/scaffold regression.
- HIGH: Policy now exposes API-to-Worker edge; unused import removed. Phase 2 still owns full process-boundary cutover.
- MEDIUM: Duplicate-model detection currently uses canonical class names and field signatures. JSON schema hash and purpose tags require canonical model metadata in Phase 5.
- MEDIUM: Top-level Plugins/Skills required by policy but intentionally scheduled for Phase 4; checker validates presence now because existing directories exist.
