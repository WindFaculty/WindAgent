# PLAN_A_HANDOFF_GATE — A7 verdict

- Contract: studio.contract/v0.1
- Gate: PLAN_A_HANDOFF_GATE
- Verdict: **PASS**
- Integration SHA: `fa3c2ac708d2b96cc6c6eb3b5c4607fb60c7af87`
- Migration head: ['0011_studio_run_nodes']

## Checks

- PASS — all_checkers_green
- PASS — migration_reaches_head_0011
- PASS — backfill_preserved
- PASS — downgrade_preserves_legacy
- PASS — reupgrade_after_rehearsal
- PASS — studio_regression_green
- PASS — a_to_b_consumer_green
- PASS — a_to_c_consumer_green
- PASS — v2_api_only_known_failures
- PASS — vp3d_blender_only_known_failures
- PASS — no_unknown_failures
- PASS — known_failures_documented
- PASS — registries_frozen
- PASS — full_matrix_only_known_failures

## Scope

- Eight Plan A checkers green on one SHA: architecture imports, event taxonomy,
  version consistency (A0 baseline failure retired by importing PRODUCT_VERSION),
  duplicate canonical models, video workspace, legacy orchestration fence,
  story-in-legacy-engine fence, secret exposure.
- Migration rehearsal through head 0011: legacy fixture backfill, downgrade to
  0009 preserving V2 rows, clean re-upgrade.
- Fresh targeted suites: Studio regression, A->B consumer, A->C consumer,
  V2 API regression, VP3D/Blender contract regression.
- Versioned handoff manifest: contract versions, migration head, event/task
  registries, known limitations, rollback commands.
- Full workspace pytest matrix + junit recorded under artifacts/ci/a7_junit.xml.

Evidence JSON: `artifacts/studio_roadmap_01/a7/evidence.json`
Generated: 2026-08-11T03:59:15.826724+00:00
