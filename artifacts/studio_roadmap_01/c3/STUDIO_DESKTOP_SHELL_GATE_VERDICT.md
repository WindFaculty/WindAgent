# STUDIO_DESKTOP_SHELL_GATE — C3 verdict

- Gate: STUDIO_DESKTOP_SHELL_GATE
- Verdict: **PASS**
- Integration SHA: `f60874e9aa6fffa26339eca67a6d34315a19d777`
- Generated: 2026-08-10T05:34:14.427329+00:00

## Checks

- PASS — desktop_suite_passes
- PASS — python_v3_contract_suite_passes
- PASS — studio_shell_uses_real_client
- PASS — hash_route_navigation_present
- PASS — no_fake_in_studio_shell
- PASS — no_sample_ids_in_studio_shell
- PASS — studio_nav_wired_in_app

## Test results

- `C:\Users\Admin\AppData\Local\hermes\node\npx.cmd vitest run --no-color` (desktop_vitest) → Tests  112 passed (112)
- `C:\Users\Admin\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe -m pytest -q tests/unit/api/test_studio_v3_api.py tests/unit/api/test_openapi_snapshot.py --no-header` (python_v3_contracts) → 33 passed in 15.60s

## Scans

- Fake-module hits in StudioPage: none
- Sample-ID hits in StudioPage: none

- StudioPage SHA256: `3906d16ef09707528a2e1906e4ab143b4d9bd652c833666a04a272b5843b28f8`

- StudioPage composes HttpStudioApiClient over VITE_API_BASE or http://localhost:8000; V2 ProductionWorkspacePage keeps its legacy fake client behind the compatibility route (baseline defect, retired at STORY_UI_GATE per 90_MASTER_ACCEPTANCE_GATES.md).

Evidence JSON: `artifacts/studio_roadmap_01/c3/evidence.json`
