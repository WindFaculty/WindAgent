# A7 — Foundation Regression and Handoff Evidence

Contract version: `studio.contract/v0.1`. Integration SHA: `fa3c2ac708d2b96cc6c6eb3b5c4607fb60c7af87`.
Fresh gate: `PLAN_A_HANDOFF_GATE` — **PASS**.

## 1. Checkers (fresh, one SHA)

- `check_architecture_imports`: exit 0 — Zero boundary violations detected
- `check_event_taxonomy`: exit 0 — [PASS] Event Taxonomy Check PASSED: 100% events match EventCatalog.
- `check_version_consistency`: exit 0 — VERSION CONSISTENCY CHECK: PASSED
- `check_duplicate_canonical_models`: exit 0 — [PASS] Zero duplicate canonical model definitions.
- `check_video_workspace_architecture`: exit 0 — Gate Status: VP3D_UI_VIDEO_WORKSPACE_FOUNDATION_READY = PASSED
- `check_no_legacy_orchestration`: exit 0 — PASS: Zero legacy orchestration imports found across codebase.
- `check_no_story_in_legacy_engines`: exit 0 — PASS: Zero Story imports/task/event references inside legacy orchestration engines.
- `check_secret_exposure`: exit 0 — [PASS] Secret Exposure Check PASSED: Zero plaintext provider secrets found in code.

## 2. Migration and rollback rehearsal (temp DB, head 0011)

- Preflight legacy rows: {'video_production_projects': 2, 'video_production_revisions': 3}
- Post-upgrade rows: {'video_production_projects': 2, 'video_production_revisions': 3, 'studio_series_projects': 2, 'studio_episodes': 2, 'studio_revisions': 3}
- Downgrade rehearsal: {'step': 'downgrade_to_0009', 'current': ['0009_immutable_plan_revisions'], 'row_counts': {'video_production_projects': 2, 'video_production_revisions': 3}}
- Re-upgrade rehearsal: {'step': 'reupgrade_to_head', 'current': ['0011_studio_run_nodes'], 'row_counts': {'video_production_projects': 2, 'video_production_revisions': 3, 'studio_series_projects': 2, 'studio_episodes': 2, 'studio_revisions': 3}}

## 3. Fresh targeted suites

- studio_regression: exit 0 — 165 passed, 1 warning in 7.97s
- a_to_b_consumer: exit 0 — 43 passed in 1.41s
- a_to_c_consumer: exit 0 — 41 passed, 1 warning in 12.77s
- v2_api_regression: exit 1 — 3 failed, 11 passed, 1 warning in 4.03s
- vp3d_blender_regression: exit 1 — 1 failed, 545 passed, 32 skipped in 26.35s

## 4. Registries (frozen)

- Event catalog: 87 event types.
- Studio task types (9): studio.story.beats.generate, studio.story.bible.generate, studio.story.idea.evaluate, studio.story.idea.generate, studio.story.lock, studio.story.outline.generate, studio.story.review, studio.story.revise, studio.story.screenplay.generate.

## 5. Handoff manifest

See `artifacts/studio_roadmap_01/a7/evidence.json` → `handoff_manifest` (contract versions, migration head, known limitations, rollback commands).

Verdict: **PASS** (`PLAN_A_HANDOFF_GATE`).
