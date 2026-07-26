# Phase 15 Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Stale `windagent.db` in repo root pollutes tests (IF NOT EXISTS keeps old schema, missing `aggregate_id`) | Was REAL | 60+ false failures | Removed stale db; tests now build fresh schema |
| Phase 14 edits regress existing tests | Was REAL | Broken CI | Caught via baseline diff; 0 net regressions after fixes |
| Frontend tests have pre-existing reds | Observed | Gate noise | Documented as known; build/type-check green |
| Package isolation broken on clean clone | Low | Import failures | All 11 pkgs import standalone (verified) |
| `windagent_deps` namespace may shadow `windagent_plugins` | Possible | Import ambiguity | Not triggered in clean import smoke; tracked |
