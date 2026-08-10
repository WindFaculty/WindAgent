# STUDIO_CLIENT_STATE_GATE — C2 verdict

- Gate: STUDIO_CLIENT_STATE_GATE
- Verdict: **PASS**
- Integration SHA: `eec23009c6ea5b4698a3ba9d788024be0b45f59c`
- Generated: 2026-08-10T05:12:41.861035+00:00

## Checks

- PASS — client_tests_pass
- PASS — state_tests_pass
- PASS — contracts_roundtrip_pass
- PASS — existing_frontend_untouched
- PASS — no_fake_in_production_src
- PASS — no_fixed_sample_ids

## Test results

- `C:\Users\Admin\AppData\Local\hermes\node\npx.cmd vitest run --no-color` (studio_client) → Tests  11 passed (11)
- `C:\Users\Admin\AppData\Local\hermes\node\npx.cmd vitest run --no-color` (studio_state) → Tests  9 passed (9)
- `C:\Users\Admin\AppData\Local\hermes\node\npx.cmd vitest run --no-color` (studio_contracts) → Tests  9 passed (9)
- `C:\Users\Admin\AppData\Local\hermes\node\npx.cmd vitest run --no-color` (production_state) → Tests  8 passed (8)

## Scans

- Fake-module hits in production src: none
- Fixed sample-ID hits in production src: none

- HttpStudioApiClient SHA256: `41f5541016df1f3e31295e7e480766138e83752239e80c3776ef6da885e572e9`
- StudioStore SHA256: `010f56b95174e203df62ba86f2931f8263421ebccf758c41cb1aeefa05a58941`

Evidence JSON: `artifacts/studio_roadmap_01/c2/evidence.json`
