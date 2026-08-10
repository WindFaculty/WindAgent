# STUDIO_PERSISTENCE_GATE — A3 verdict

- Contract: studio.contract/v0.1
- Gate: STUDIO_PERSISTENCE_GATE
- Verdict: **PASS**
- Migration: 0010_studio_persistence (sha256 c1550613ad6a1bd2...)
- Current head: ['0010_studio_persistence']

## Checks

- PASS — fresh_upgrade_reaches_head
- PASS — backfill_series_episodes_revisions
- PASS — legacy_rows_preserved_on_downgrade
- PASS — reupgrade_after_rehearsal
- PASS — repository_contract_tests_pass

## Scope

- Additive migration 0010: 8 Studio tables + 5 uniqueness indexes + outbox per-aggregate ordering index.
- Deterministic backfill of legacy projects/revisions; no invented story content.
- Repositories behind A2 ports with dual-read compatibility and optimistic concurrency.
- StudioUnitOfWork: atomic aggregates/events/outbox with per-aggregate event sequences.
- Downgrade rehearsal verified: legacy V2 rows untouched, re-upgrade clean.

Evidence JSON: `artifacts/studio_roadmap_01/a3/evidence.json`
Generated: 2026-08-09T17:50:05.170283+00:00
