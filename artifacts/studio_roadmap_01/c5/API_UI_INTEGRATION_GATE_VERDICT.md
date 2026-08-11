# API_UI_INTEGRATION_GATE — C5 verdict

- Gate: API_UI_INTEGRATION_GATE
- Verdict: **PASS**
- Integration SHA: `68e3e65cd6a508d249b32cb73b9cf6e364649ce2`
- Generated: 2026-08-11T00:36:21.730585+00:00

## Checks

- PASS — desktop_suite_passes
- PASS — python_v3_contract_suite_passes
- PASS — screenplay_views_present
- PASS — screenplay_renders_traceability
- PASS — review_findings_render_code_severity_location
- PASS — diff_compares_before_after_drafts
- PASS — hash_bound_lock_command
- PASS — screenplay_checkpoint_wired
- PASS — post_lock_read_only
- PASS — c5_workflow_tests_present
- PASS — no_fake_or_sample_ids_in_studio_sources

## Test results

- `C:\Users\Admin\AppData\Local\hermes\node\npx.cmd vitest run --no-color` (desktop_vitest) → Tests  142 passed (142)
- `C:\Users\Admin\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe -m pytest -q tests/unit/api/test_studio_v3_api.py tests/unit/api/test_openapi_snapshot.py --no-header` (python_v3_contracts) → 33 passed in 71.46s (0:01:11)

## Scans

- Fake/sample-ID hits in Studio sources: none

## File checksums

- `StudioPage.tsx`: `ad515175faa2031b610b6fea64666683a971e99eacb2c3f5431f973c83ffc097`
- `ArtifactViews.tsx`: `94a514f443fc403c24ba51fcb86563ce27638a057a8adf6152452f5fc6693424`
- `studioStoryTests.test.tsx`: `0e9b8b29530eaf134896ae09e4802ba3bc93cdabcf43c9cb241318ee303951e6`

- Screenplay/review/revision/lock UI renders server artifacts only: structured draft with canon/beat traceability, review findings with code/severity/location, immutable before/after revision diff, lock receipt + package lineage. Lock and approval commands carry the exact server revision content hash and expected version; after lock the episode view is read-only and corrections route through a new run. No local stage advance, no synthesized artifact, no fake client.

Evidence JSON: `artifacts/studio_roadmap_01/c5/evidence.json`
